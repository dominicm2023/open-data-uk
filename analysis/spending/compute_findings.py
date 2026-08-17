"""Compute findings.json from corpus.db.

Every number in REPORT.md traces back to a query in this file.
"""
import json
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def council_coverage(publishers_with_rows):
    """Match corpus publishers against the 361-council register (name substring,
    both directions, on lowercased names with council-word noise stripped)."""
    councils = json.loads((ROOT / "councils.json").read_text(encoding="utf-8"))

    def squash(s):
        s = s.lower()
        s = re.sub(r"\b(london borough of|royal borough of|city of|council of|"
                   r"metropolitan|borough|district|county|city|council|the|of|"
                   r"upon|and)\b", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    NOT_A_COUNCIL = re.compile(r"nhs|hospital|foundation trust|ccg|icb|"
                               r"ambulance|transport for", re.I)
    pubs = {p: squash(p) for p in publishers_with_rows
            if not NOT_A_COUNCIL.search(p)}
    matched = {}
    for c in councils:
        cs = squash(c["name"])
        if not cs:
            continue
        cw = cs.split()
        for p, ps in pubs.items():
            pw = ps.split()
            # whole-word sequence match, either direction
            if cs == ps or any(pw[i:i + len(cw)] == cw
                               for i in range(len(pw) - len(cw) + 1)):
                matched[c["name"]] = p
                break
    return {
        "register_size": len(councils),
        "councils_in_corpus": len(matched),
        "matches": matched,
        "non_council_publishers": sorted(
            p for p in publishers_with_rows if p not in matched.values()),
    }


# The headline set: not a cross-file duplicate, supplier not blank.
CLEAN = "is_dup=0 AND supplier_raw<>''"


def reconciliation(con):
    """Raw total -> after dedupe -> after subtotal removal -> after unit
    fixes, with the out-of-window date rows (dropped at parse) shown too."""
    step = {}
    raw = con.execute(
        "SELECT COUNT(*), ROUND(SUM(amount),2) FROM transactions").fetchone()
    step["raw_parsed"] = {"rows": raw[0], "gbp": raw[1]}
    dup = con.execute("SELECT COUNT(*), ROUND(SUM(amount),2) FROM transactions "
                      "WHERE is_dup=1").fetchone()
    step["cross_file_duplicates_removed"] = {"rows": dup[0], "gbp": dup[1]}
    sub = con.execute("SELECT COUNT(*), ROUND(SUM(amount),2) FROM transactions "
                      "WHERE is_dup=0 AND supplier_raw=''").fetchone()
    step["blank_supplier_rows_removed"] = {"rows": sub[0], "gbp": sub[1]}
    clean = con.execute(f"SELECT COUNT(*), ROUND(SUM(amount),2) FROM transactions "
                        f"WHERE {CLEAN}").fetchone()
    step["clean"] = {"rows": clean[0], "gbp": clean[1]}

    # out-of-window dates were dropped at parse time; counted in files.note
    oor_n = oor_gbp = 0
    for (note,) in con.execute(
            "SELECT note FROM files WHERE note LIKE '%oor_dates=%'"):
        m = re.search(r"oor_dates=(\d+) oor_gbp=([\d.\-]+)", note)
        if m:
            oor_n += int(m.group(1))
            oor_gbp += float(m.group(2))
    step["out_of_window_dates_dropped_at_parse"] = {
        "rows": oor_n, "gbp": round(oor_gbp, 2)}

    # pence-vs-pounds suspects: a file whose median is >=100x the median of
    # its OWN dataset series (files in a series share a template; comparing
    # against the publisher misfires when one publisher mixes GPC-over-£500
    # and spend-over-£25k series). Series needs >=3 files, file >=20 rows.
    file_meds = {}
    for ds, sf, n in con.execute(
            f"SELECT dataset_key, source_file, COUNT(*) FROM transactions "
            f"WHERE {CLEAN} GROUP BY dataset_key, source_file "
            f"HAVING COUNT(*) >= 20"):
        med = con.execute(
            f"SELECT amount FROM transactions WHERE source_file=? AND {CLEAN} "
            f"ORDER BY amount LIMIT 1 OFFSET ?", (sf, n // 2)).fetchone()[0]
        file_meds.setdefault(ds, []).append((sf, n, med))
    suspects = []
    for ds, items in file_meds.items():
        if len(items) < 3:
            continue
        meds = sorted(m for _, _, m in items)
        ds_median = meds[len(meds) // 2]
        if ds_median <= 0:
            continue
        for sf, n, med in items:
            if med >= 100 * ds_median:
                pub, gbp = con.execute(
                    f"SELECT publisher, ROUND(SUM(amount),2) FROM transactions "
                    f"WHERE source_file=? AND {CLEAN}", (sf,)).fetchone()
                suspects.append({"publisher": pub, "dataset_key": ds,
                                 "file": sf, "rows": n, "file_median": med,
                                 "series_median": ds_median, "gbp": gbp})
    # Hand-checked during the build: every flagged file so far was a genre
    # mixture (an over-£25k-shaped file inside a series that publishes every
    # transaction down to pennies), NOT a pence-for-pounds error. So no unit
    # adjustment is applied to the headline; the list is a hand-check queue.
    step["scale_outlier_files_for_hand_checking"] = suspects
    return step


def main():
    con = sqlite3.connect(HERE / "corpus.db")
    con.row_factory = sqlite3.Row
    con.execute("CREATE INDEX IF NOT EXISTS ix_t_sf ON transactions(source_file)")
    con.commit()
    f = {}

    f["totals"] = dict(con.execute(f"""
        SELECT COUNT(*) AS transactions, ROUND(SUM(amount),2) AS gbp_total,
               MIN(date) AS first_date, MAX(date) AS last_date,
               COUNT(DISTINCT publisher) AS publishers,
               SUM(date IS NULL) AS undated_rows
        FROM transactions WHERE {CLEAN}""").fetchone())

    f["reconciliation"] = reconciliation(con)

    f["by_year_month"] = [dict(r) for r in con.execute(f"""
        SELECT year_month, COUNT(*) AS n, ROUND(SUM(amount),2) AS gbp
        FROM transactions WHERE year_month IS NOT NULL AND {CLEAN}
        GROUP BY year_month ORDER BY year_month""")]

    medians = {}
    for (pub,) in con.execute(
            f"SELECT DISTINCT publisher FROM transactions WHERE {CLEAN}"):
        n = con.execute(f"SELECT COUNT(*) FROM transactions "
                        f"WHERE publisher=? AND {CLEAN}", (pub,)).fetchone()[0]
        medians[pub] = con.execute(
            f"SELECT amount FROM transactions WHERE publisher=? AND {CLEAN} "
            f"ORDER BY amount LIMIT 1 OFFSET ?", (pub, n // 2)).fetchone()[0]

    f["per_publisher"] = [dict(r) for r in con.execute(f"""
        SELECT fl.publisher,
               COUNT(*) AS files,
               SUM(fl.status='parsed') AS files_parsed,
               ROUND(1.0*SUM(fl.status='parsed')/COUNT(*),3) AS parse_rate,
               t.first_date, t.last_date, t.gbp_total, t.tx
        FROM files fl
        LEFT JOIN (
          SELECT publisher, MIN(date) AS first_date, MAX(date) AS last_date,
                 ROUND(SUM(amount),2) AS gbp_total, COUNT(*) AS tx
          FROM transactions WHERE {CLEAN} GROUP BY publisher
        ) t ON t.publisher = fl.publisher
        GROUP BY fl.publisher ORDER BY t.gbp_total DESC NULLS LAST""")]
    for row in f["per_publisher"]:
        row["median_amount"] = medians.get(row["publisher"])

    f["failure_census"] = [dict(r) for r in con.execute("""
        SELECT status, COUNT(*) AS files FROM files
        GROUP BY status ORDER BY files DESC""")]
    f["failure_detail"] = {
        "fetch_errors": [dict(r) for r in con.execute("""
            SELECT note, COUNT(*) AS n FROM files WHERE status='fetch-failed'
            GROUP BY note ORDER BY n DESC""")],
        "mojibake_files": con.execute("""
            SELECT COUNT(*) FROM files WHERE note LIKE '%replacement_chars%'
            """).fetchone()[0],
        "cp1252_files": con.execute("""
            SELECT COUNT(*) FROM files WHERE note LIKE '%enc=cp1252%'
            """).fetchone()[0],
        "mdy_date_files": con.execute("""
            SELECT COUNT(*) FROM files WHERE note LIKE '%datestyle=mdy%'
            """).fetchone()[0],
    }

    f["largest_transactions"] = [dict(r) for r in con.execute(f"""
        SELECT publisher, date, supplier_raw, amount, source_file
        FROM transactions WHERE {CLEAN}
        ORDER BY amount DESC LIMIT 10""")]

    f["negative_rows"] = con.execute(
        f"SELECT COUNT(*), ROUND(SUM(amount),2) FROM transactions "
        f"WHERE amount<0 AND {CLEAN}"
    ).fetchone()
    f["negative_rows"] = {"n": f["negative_rows"][0], "gbp": f["negative_rows"][1]}

    pubs_with_rows = [r[0] for r in con.execute(
        f"SELECT DISTINCT publisher FROM transactions WHERE {CLEAN}")]
    f["council_coverage"] = council_coverage(pubs_with_rows)

    (HERE / "findings.json").write_text(
        json.dumps(f, indent=1, default=str), encoding="utf-8")
    t = f["totals"]
    print(f"transactions={t['transactions']:,} gbp={t['gbp_total']:,} "
          f"span={t['first_date']}..{t['last_date']} publishers={t['publishers']}")


if __name__ == "__main__":
    main()
