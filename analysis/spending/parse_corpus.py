"""Parse fetched spending CSVs into corpus.db.

Per file:
  - reject non-text by magic bytes (PK\\x03\\x04 = xlsx, OLE = xls, %PDF, '<' = HTML)
  - decode utf-8-sig first, cp1252 fallback; count replacement characters
  - sniff delimiter from candidate header line
  - find the header row within the first 30 lines (files carry preamble junk)
  - map columns to date / supplier / amount / expense type / expense area
  - infer date format PER FILE (a file with day>12 anywhere is d/m/Y; ISO
    detected by shape), never per row
  - amounts: strip GBP signs and thousands commas; (123) and -123 negative;
    blank/dash/text -> skipped row
  - drop running-total rows: supplier empty AND amount equals the column sum
    of the rows above (checked against full-file sum)

supplier_raw is stored VERBATIM. No normalisation here, by design.

Output: corpus.db with tables transactions and files.
Failure categories recorded per file in files.status/note:
  parsed | empty | not-csv-<sniff> | undecodable | no-header |
  no-amount-column | no-supplier-column | no-rows-parsed
"""
import csv
import io
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"

csv.field_size_limit(10_000_000)

# ---------- column recognition ----------

def norm_col(c):
    return re.sub(r"[^a-z0-9 ]", " ", (c or "").lower()).strip()

DATE_COLS = ["payment date", "date of payment", "transaction date", "date paid",
             "paid date", "invoice date", "date", "trans date", "payment created date",
             "effective date", "clearing date", "posting date", "doc date"]
SUPPLIER_COLS = ["supplier name", "supplier", "vendor name", "vendor", "payee",
                 "beneficiary", "merchant name", "merchant", "creditor name",
                 "creditor", "recipient", "supplier vendor", "trader name"]
# Bristol's template titles its supplier column just "Name". Exact match ONLY:
# as a substring it swallows "Organisation Name" / "Case Name" in
# spend-approvals files, which are not payments.
SUPPLIER_EXACT = ["name"]
AMOUNT_COLS = ["amount", "amount paid", "net amount", "invoice amount", "amount gbp",
               "gross amount", "payment amount", "value", "net value", "gross value",
               "total", "total amount", "sum of amount", "amount excluding vat",
               "amount ex vat", "net expenditure", "transaction amount",
               "invoice value", "billing gross amount", "original gross amount",
               "trans value", "gbp amount", "amount in sterling", "spend"]
ETYPE_COLS = ["expense type", "expenses type", "expenditure type", "type of expenditure",
              "category", "spend category", "expense category", "subjective",
              "detailed expenditure type", "purpose of expenditure", "description",
              "merchant category", "transaction description", "narrative"]
EAREA_COLS = ["expense area", "expenses area", "expenditure area", "service area",
              "directorate", "department", "service", "cost centre description",
              "department family", "division", "portfolio", "service division"]
TXN_COLS = ["transaction number", "transaction ref", "transaction no",
            "transaction id", "trans no", "invoice number", "invoice no",
            "payment reference", "reference"]

DATE_MIN, DATE_MAX = "2008-01-01", "2026-08-17"  # analysis window (today)


def pick(cols_norm, wanted):
    """Term priority beats match tightness ACROSS terms; within a term,
    exact beats startswith beats substring."""
    for w in wanted:
        for i, c in enumerate(cols_norm):
            if c == w:
                return i
        for i, c in enumerate(cols_norm):
            if c.startswith(w):
                return i
        for i, c in enumerate(cols_norm):
            if w in c:
                return i
    return None


def pick_candidates(cols_norm, wanted):
    """All matching column indexes, in term-priority order, deduped."""
    out = []
    for w in wanted:
        for i, c in enumerate(cols_norm):
            if w in c and i not in out:
                out.append(i)
    return out


def pick_amount(cols_norm, data_rows):
    """Pick the first amount-named column whose values are mostly numeric."""
    for i in pick_candidates(cols_norm, AMOUNT_COLS):
        vals = [r[i].strip() for r in data_rows[:200]
                if len(r) > i and r[i].strip()]
        if not vals:
            continue
        numeric = sum(1 for v in vals if parse_amount(v) is not None)
        # zero-padded integers ("0050037090") are transaction numbers that
        # land under an "Amount" header when data rows carry more columns
        # than the header names (seen at NHSBSA) — an id column, not money
        idlike = sum(1 for v in vals if len(v) > 5 and v.startswith("0")
                     and "." not in v and "," not in v)
        if idlike > len(vals) * 0.3:
            continue
        if numeric >= max(1, len(vals) // 2):
            return i
    # Fallback for headers like a bare "£": an unnamed column whose values
    # are >=90% numeric AND look like money (decimals/thousands separators),
    # so transaction-number columns don't qualify.
    for i, c in enumerate(cols_norm):
        if c:
            continue
        vals = [r[i] for r in data_rows[:200] if len(r) > i and r[i].strip()]
        if len(vals) < 3:
            continue
        numeric = sum(1 for v in vals if parse_amount(v) is not None)
        moneyish = sum(1 for v in vals if "." in v or "," in v)
        if numeric >= len(vals) * 0.9 and moneyish >= len(vals) * 0.1:
            return i
    return None


# ---------- amount parsing ----------

AMOUNT_JUNK = re.compile(r"[£$€,\s ]")

def parse_amount(s):
    if s is None:
        return None
    s = s.strip()
    if not s or s in {"-", "--", "n/a", "N/A", "NULL"}:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    s = AMOUNT_JUNK.sub("", s)
    if s.endswith("-"):  # SAP-style trailing minus
        neg = True
        s = s[:-1]
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


# ---------- date parsing ----------

ISO_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
COMPACT_RE = re.compile(r"^(19|20)\d{6}$")
SLASH_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})$")
DMY_TEXT_RE = re.compile(r"^(\d{1,2})[ \-]([A-Za-z]{3,9})[ \-](\d{2,4})$")
MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def detect_date_style(samples):
    """Return 'iso', 'dmy', 'mdy', or 'text' from a list of date strings."""
    iso = slash = 0
    dmy_evidence = mdy_evidence = 0
    for s in samples:
        s = s.strip()
        if ISO_RE.match(s) or COMPACT_RE.match(s):
            iso += 1
            continue
        m = SLASH_RE.match(s)
        if m:
            slash += 1
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                dmy_evidence += 1
            if b > 12:
                mdy_evidence += 1
    if iso > slash:
        return "iso"
    if slash:
        if mdy_evidence and not dmy_evidence:
            return "mdy"
        return "dmy"  # UK default; also covers explicit dmy evidence
    return "text"


def parse_date(s, style):
    if not s:
        return None
    s = s.strip()
    m = ISO_RE.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return check(y, mo, d)
    if COMPACT_RE.match(s):
        return check(int(s[:4]), int(s[4:6]), int(s[6:8]))
    m = SLASH_RE.match(s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 70 else 1900
        if style == "mdy" and a <= 12:
            mo, d = a, b
        else:
            d, mo = a, b
            if mo > 12 and d <= 12:  # per-cell rescue when file signal was wrong
                d, mo = mo, d
        return check(y, mo, d)
    m = DMY_TEXT_RE.match(s)
    if m:
        mo = MONTHS.get(m.group(2)[:3].lower())
        if mo:
            y = int(m.group(3))
            if y < 100:
                y += 2000 if y < 70 else 1900
            return check(y, mo, int(m.group(1)))
    # Excel serial dates sneak into CSV exports
    if s.isdigit() and 30000 < int(s) < 60000:
        from datetime import date, timedelta
        dt = date(1899, 12, 30) + timedelta(days=int(s))
        return dt.isoformat()
    return None


def check(y, mo, d):
    try:
        datetime(y, mo, d)
    except ValueError:
        return None
    if not (1990 <= y <= 2099):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


# ---------- file-level parsing ----------

def sniff_bytes(b):
    if b.startswith(b"PK\x03\x04"):
        return "xlsx-zip"
    if b.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls-ole"
    if b.startswith(b"%PDF"):
        return "pdf"
    if b.lstrip()[:1] == b"<":
        return "html-or-xml"
    return "text"


def decode(raw):
    """Return (text, encoding, replacement_count)."""
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        txt = raw.decode("utf-16", errors="replace")
        return txt, "utf-16", txt.count("�")
    try:
        return raw.decode("utf-8-sig"), "utf-8-sig", 0
    except UnicodeDecodeError:
        pass
    txt = raw.decode("cp1252", errors="replace")
    return txt, "cp1252", txt.count("�")


def find_header(lines, delim_hint=None):
    """Return (header_row_index, delimiter) or (None, None)."""
    best = (None, None, 0)
    for i, line in enumerate(lines[:30]):
        for delim in ([delim_hint] if delim_hint else [",", ";", "\t", "|"]):
            try:
                cells = next(csv.reader([line], delimiter=delim))
            except (csv.Error, StopIteration):
                continue
            if len(cells) < 3:
                continue
            if max(len(c) for c in cells) > 200:
                continue  # preamble blobs are never header cells
            cn = [norm_col(c) for c in cells]
            score = 0.0
            if pick(cn, SUPPLIER_COLS) is not None or "name" in cn:
                score += 2
            if pick(cn, AMOUNT_COLS) is not None:
                score += 2
            if pick(cn, DATE_COLS) is not None:
                score += 1
            # real headers have mostly non-empty cells; preamble rows don't
            score += sum(1 for c in cells if c.strip()) / len(cells)
            if score > best[2]:
                best = (i, delim, score)
    if best[2] >= 2:  # a plausible header; column checks classify precisely
        return best[0], best[1]
    return None, None


def parse_file(path, meta):
    """Return (status, note, rows, parsed, skipped). rows = list of tuples."""
    raw = path.read_bytes()
    if len(raw) == 0:
        return "empty", None, [], 0, 0
    kind = sniff_bytes(raw[:512])
    if kind != "text":
        return f"not-csv-{kind}", None, [], 0, 0
    text, enc, repl = decode(raw)
    lines = text.splitlines()
    if not lines:
        return "empty", None, [], 0, 0
    hdr_i, delim = find_header(lines)
    if hdr_i is None:
        return "no-header", f"enc={enc}", [], 0, 0

    reader = csv.reader(io.StringIO("\n".join(lines[hdr_i:])), delimiter=delim)
    try:
        header = next(reader)
    except StopIteration:
        return "empty", None, [], 0, 0
    cn = [norm_col(c) for c in header]
    data_rows = list(reader)
    i_sup = pick(cn, SUPPLIER_COLS)
    if i_sup is None and "name" in cn:
        i_sup = cn.index("name")
    i_amt = pick_amount(cn, data_rows)
    i_date = pick(cn, DATE_COLS)
    i_et = pick(cn, ETYPE_COLS)
    i_ea = pick(cn, EAREA_COLS)
    i_txn = pick(cn, TXN_COLS)
    if i_amt is None:
        return "no-amount-column", f"enc={enc} cols={header[:8]}", [], 0, 0
    if i_sup is None:
        return "no-supplier-column", f"enc={enc} cols={header[:8]}", [], 0, 0
    # avoid mapping the same column to both expense fields
    if i_et is not None and i_et in (i_sup, i_amt, i_date):
        i_et = None
    if i_ea is not None and i_ea in (i_sup, i_amt, i_date, i_et):
        i_ea = None

    # per-file date style
    style = "text"
    if i_date is not None:
        samples = [r[i_date] for r in data_rows[:400] if len(r) > i_date and r[i_date].strip()]
        style = detect_date_style(samples)

    rows, parsed, skipped = [], 0, 0
    oor_dates, oor_gbp = 0, 0.0
    amounts_sum = 0.0
    pending = []
    for r in data_rows:
        if not any(c.strip() for c in r):
            continue
        sup = r[i_sup].strip() if len(r) > i_sup else ""
        amt = parse_amount(r[i_amt]) if len(r) > i_amt else None
        if amt is None:
            skipped += 1
            continue
        date = parse_date(r[i_date], style) if (i_date is not None and len(r) > i_date) else None
        if date is not None and not (DATE_MIN <= date <= DATE_MAX):
            oor_dates += 1
            oor_gbp += amt
            skipped += 1
            continue
        et = r[i_et].strip() if (i_et is not None and len(r) > i_et) else None
        ea = r[i_ea].strip() if (i_ea is not None and len(r) > i_ea) else None
        txn = r[i_txn].strip() if (i_txn is not None and len(r) > i_txn) else None
        pending.append((sup, amt, date, et, ea, txn))
        amounts_sum += amt

    for sup, amt, date, et, ea, txn in pending:
        # running-total row: empty supplier and amount ~ sum of everything else
        if not sup and abs(amounts_sum - 2 * amt) < 0.01 and len(pending) > 2:
            skipped += 1
            continue
        ym = date[:7] if date else None
        rows.append((meta["publisher"], meta["dataset_key"], path.name,
                     date, ym, sup, round(amt, 2), et or None, ea or None,
                     txn or None))
        parsed += 1

    if parsed == 0:
        return "no-rows-parsed", f"enc={enc} skipped={skipped}", [], 0, skipped
    note = f"enc={enc}"
    if repl:
        note += f" replacement_chars={repl}"
    if style != "text":
        note += f" datestyle={style}"
    if oor_dates:
        note += f" oor_dates={oor_dates} oor_gbp={round(oor_gbp, 2)}"
    return "parsed", note, rows, parsed, skipped


# Spend-approvals / exceptions-to-moratoria publications matched the title
# filter's "spend" but are a different genre: they record permission to spend
# (often in £M), not payments made. Excluded wholesale, censused as such.
APPROVALS_TITLE = re.compile(r"exception|moratori|control data|"
                             r"spending approvals|spend control", re.I)


def main():
    manifest = json.loads((HERE / "manifest.json").read_text(encoding="utf-8"))
    db = HERE / "corpus.db"
    db.unlink(missing_ok=True)
    con = sqlite3.connect(db)
    con.executescript("""
    CREATE TABLE transactions(
      publisher TEXT, dataset_key TEXT, source_file TEXT,
      date TEXT, year_month TEXT, supplier_raw TEXT,
      amount REAL, expense_type TEXT, expense_area TEXT,
      txn TEXT,          -- transaction number as printed, for dedupe
      is_dup INTEGER DEFAULT 0  -- cross-file duplicate, set by dedupe_flag.py
    );
    CREATE TABLE files(
      url TEXT PRIMARY KEY, publisher TEXT,
      parsed_rows INTEGER, skipped_rows INTEGER,
      status TEXT, note TEXT);
    """)
    n = 0
    for url, rec in manifest.items():
        n += 1
        if n % 500 == 0:
            print(f"...{n} files", flush=True)
            con.commit()
        pub = rec.get("publisher")
        if not rec.get("file"):
            con.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)",
                        (url, pub, 0, 0, "fetch-failed",
                         rec.get("error") or f"http-{rec.get('http_status')}"))
            continue
        path = RAW / rec["file"]
        if not path.exists():
            con.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)",
                        (url, pub, 0, 0, "fetch-failed", "file-missing"))
            continue
        if APPROVALS_TITLE.search(rec.get("title") or ""):
            con.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)",
                        (url, pub, 0, 0, "excluded-approvals-dataset",
                         (rec.get("title") or "")[:80]))
            continue
        meta = {"publisher": pub, "dataset_key": rec["dataset_key"]}
        try:
            status, note, rows, parsed, skipped = parse_file(path, meta)
        except Exception as e:  # noqa: BLE001 — census the wreckage, don't die
            status, note, rows, parsed, skipped = ("parse-exception",
                                                   f"{type(e).__name__}: {e}", [], 0, 0)
        if rows:
            con.executemany(
                "INSERT INTO transactions VALUES(?,?,?,?,?,?,?,?,?,?,0)", rows)
        con.execute("INSERT OR REPLACE INTO files VALUES(?,?,?,?,?,?)",
                    (url, pub, parsed, skipped, status, note))
    con.commit()
    con.execute("CREATE INDEX ix_t_pub ON transactions(publisher)")
    con.execute("CREATE INDEX ix_t_ym ON transactions(year_month)")
    con.commit()
    for row in con.execute("SELECT status, COUNT(*) FROM files GROUP BY status ORDER BY 2 DESC"):
        print(row)
    print("transactions:", con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])


if __name__ == "__main__":
    main()
