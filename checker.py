"""Resource availability checker: verifies what's actually behind dataset
links, because most catalogue entries lead to a webpage, not a data file.

Verdicts:

    data     verified direct data file (CSV, JSON, spreadsheet, archive, ...)
    webpage  the link works but serves HTML — more clicking required
    api      a service endpoint (WMS/WFS/OGC, REST APIs)
    dead     the link is genuinely broken (404/410/500, or won't connect)
    blocked  the publisher refused *us* (429/403/401/503) — we do NOT know
             whether the data is there, and must not claim it's dead

That last distinction matters. An earlier version recorded 429s and 403s as
"dead", so a slice of 2,500 checks came back 58% dead — but 56% of those
were publishers throttling or bot-blocking us, concentrated on a handful of
hosts we were hammering. Telling users a council's data is broken when it
is fine is both wrong and unfair to the publisher.

So we are deliberately polite: requests to any single host are spaced out
(see DomainThrottle) and the work list is interleaved across hosts, which
both keeps the worker pool busy and stops us stampeding one server.

For CSV files it also peeks at the first bytes and extracts column names —
shown in search results so users can judge relevance without downloading.

Dataset-level availability is aggregated onto datasets.availability, best
verdict wins: data > api > webpage > blocked > dead. "blocked" outranks
"dead" on purpose — if any resource is merely unverifiable we decline to
call the dataset dead.

Usage:
    python checker.py --limit 2500          # nightly rolling slice
    python checker.py --first-only          # one resource per dataset
    python checker.py --recheck-blocked     # re-examine past false "dead"s
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
import threading
import time
import urllib.parse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from paths import DB_PATH, connect as db_connect

# Identify ourselves honestly, with a contact URL — the conventional polite
# -bot format, and far less likely to trip a WAF than a bare tool token.
UA = ("Mozilla/5.0 (compatible; uk-open-data-index/0.2; "
      "+https://data.groundwatercast.com/about)")
TIMEOUT = 12
CSV_PEEK_BYTES = 16384
MAX_COLUMNS = 40

DOMAIN_INTERVAL = 1.5   # seconds between requests to the same host
MAX_PER_DOMAIN = 250    # per run, so one big portal can't eat the whole slice
RETRY_AFTER_CAP = 10    # honour Retry-After only if it's this short

DATA_TYPES = (
    "text/csv", "application/csv", "application/json", "application/geo+json",
    "application/vnd.geo+json", "application/zip", "application/x-zip",
    "application/gzip", "application/vnd.ms-excel", "application/parquet",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.spreadsheet", "application/xml",
    "text/xml", "application/rdf+xml", "text/turtle", "application/pdf",
    "application/octet-stream", "application/x-netcdf", "image/tiff",
)
API_HINTS = ("wms", "wfs", "wmts", "arcgis", "geoserver", "/rest/", "ogc",
             "sparql", "service=", "/api/")

# Refusals aimed at us, not evidence about the data
BLOCKED_STATUSES = {401, 403, 429, 503}

SCHEMA = """
CREATE TABLE IF NOT EXISTS resource_checks (
    url          TEXT PRIMARY KEY,
    status       INTEGER,
    content_type TEXT,
    size_bytes   INTEGER,
    verdict      TEXT NOT NULL,
    columns      TEXT,          -- JSON list of CSV column names, if peeked
    checked_at   TEXT NOT NULL
);
"""


def domain_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


class DomainThrottle:
    """Reserve a time slot per host so we never stampede one server.

    Workers call wait() before each request; it hands out slots spaced
    DOMAIN_INTERVAL apart per domain and sleeps the caller until its turn.
    Different domains never block each other, so the pool stays busy.
    """

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._next_free: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, domain: str) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(self._next_free.get(domain, now), now)
            self._next_free[domain] = slot + self.min_interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def classify(url: str, status: int, ctype: str, fmt: str | None) -> str:
    if status in BLOCKED_STATUSES:
        return "blocked"
    if status == 0 or status >= 400:
        return "dead"
    lower_url = url.lower()
    if any(h in lower_url for h in API_HINTS) or (fmt or "") in ("WMS", "WFS", "API", "SPARQL"):
        return "api"
    base = ctype.split(";")[0].strip().lower()
    if base.startswith(DATA_TYPES):
        return "data"
    if base in ("text/html", "application/xhtml+xml", ""):
        return "webpage"
    if base.startswith(("text/", "image/", "application/")):
        return "data"  # some concrete file type we didn't enumerate
    return "webpage"


def peek_csv_columns(session: requests.Session, url: str) -> list[str] | None:
    try:
        r = session.get(url, timeout=TIMEOUT, stream=True,
                        headers={"Range": f"bytes=0-{CSV_PEEK_BYTES - 1}"})
        chunk = next(r.iter_content(CSV_PEEK_BYTES), b"")
        r.close()
        text = chunk.decode("utf-8-sig", errors="replace")
        first_line = text.splitlines()[0] if text.splitlines() else ""
        if not first_line:
            return None
        cols = next(csv.reader(io.StringIO(first_line)))
        cols = [c.strip()[:60] for c in cols if c.strip()]
        # a real header row: several short, non-numeric-looking fields
        if len(cols) >= 2 and sum(c.replace(".", "").isdigit() for c in cols) < len(cols) / 2:
            return cols[:MAX_COLUMNS]
    except Exception:  # noqa: BLE001
        pass
    return None


def check_one(url: str, fmt: str | None, throttle: DomainThrottle) -> dict:
    session = requests.Session()
    session.headers["User-Agent"] = UA
    domain = domain_of(url)

    def fetch() -> tuple[int, str, int | None, str | None]:
        throttle.wait(domain)
        r = session.head(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code in (405, 501):  # server refuses HEAD
            throttle.wait(domain)
            r = session.get(url, timeout=TIMEOUT, stream=True)
            r.close()
        cl = r.headers.get("content-length")
        return (r.status_code, r.headers.get("content-type", ""),
                int(cl) if cl and cl.isdigit() else None,
                r.headers.get("retry-after"))

    status, ctype, size = 0, "", None
    try:
        status, ctype, size, retry_after = fetch()
        # One polite retry if they told us exactly how long to wait
        if status == 429 and retry_after and retry_after.isdigit():
            wait = int(retry_after)
            if wait <= RETRY_AFTER_CAP:
                time.sleep(wait)
                status, ctype, size, _ = fetch()
    except Exception:  # noqa: BLE001
        pass

    verdict = classify(url, status, ctype, fmt)
    columns = None
    if verdict == "data" and (fmt == "CSV" or "csv" in ctype.lower()):
        if size is None or size < 200_000_000:
            columns = peek_csv_columns(session, url)
    return {
        "url": url, "status": status, "content_type": ctype.split(";")[0][:100],
        "size_bytes": size, "verdict": verdict,
        "columns": json.dumps(columns) if columns else None,
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def interleave_by_domain(rows: list[tuple], max_per_domain: int) -> list[tuple]:
    """Round-robin the work list across hosts, capping each host's share.

    Sequential-by-domain input would have every worker hitting one server at
    once, then all moving on together — exactly the pattern that got us
    rate-limited.
    """
    buckets: OrderedDict[str, list[tuple]] = OrderedDict()
    for row in rows:
        buckets.setdefault(domain_of(row[0]), []).append(row)
    for d in buckets:
        del buckets[d][max_per_domain:]

    out: list[tuple] = []
    while buckets:
        for d in list(buckets):
            out.append(buckets[d].pop(0))
            if not buckets[d]:
                del buckets[d]
    return out


def pick_urls(conn: sqlite3.Connection, limit: int, first_only: bool,
              recheck_blocked: bool) -> list[tuple]:
    if recheck_blocked:
        # Anything we previously recorded as blocked, plus the false "dead"s
        # from before this distinction existed (403/429/401/503 recorded as
        # dead by the older classifier).
        q = """
            SELECT r.url, r.format_norm FROM resources r
            JOIN resource_checks c ON c.url = r.url
            WHERE c.verdict = 'blocked'
               OR (c.verdict = 'dead' AND c.status IN (401, 403, 429, 503))
            LIMIT ?
        """
    elif first_only:
        # one representative resource per dataset: the first by rowid
        q = """
            SELECT r.url, r.format_norm FROM resources r
            JOIN (SELECT dataset_key, MIN(rowid) mr FROM resources GROUP BY dataset_key) f
              ON r.rowid = f.mr
            LEFT JOIN resource_checks c ON c.url = r.url
            WHERE c.url IS NULL
            LIMIT ?
        """
    else:
        # Unchecked first; blocked ones come round again sooner than settled
        # verdicts, since "blocked" is an open question rather than an answer.
        q = """
            SELECT DISTINCT r.url, r.format_norm FROM resources r
            LEFT JOIN resource_checks c ON c.url = r.url
            WHERE c.url IS NULL
               OR (c.verdict = 'blocked' AND c.checked_at < datetime('now', '-3 days'))
               OR c.checked_at < datetime('now', '-30 days')
            LIMIT ?
        """
    return conn.execute(q, (limit,)).fetchall()


def aggregate_availability(conn: sqlite3.Connection) -> None:
    """Roll resource verdicts up to datasets.availability.

    'blocked' deliberately outranks 'dead': if we couldn't verify a
    resource, we decline to tell the user the dataset is broken.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(datasets)")}
    if "availability" not in cols:
        conn.execute("ALTER TABLE datasets ADD COLUMN availability TEXT")
    conn.execute("""
        UPDATE datasets SET availability = (
            SELECT CASE
                WHEN SUM(c.verdict = 'data') > 0 THEN 'data'
                WHEN SUM(c.verdict = 'api') > 0 THEN 'api'
                WHEN SUM(c.verdict = 'webpage') > 0 THEN 'webpage'
                WHEN SUM(c.verdict = 'blocked') > 0 THEN 'blocked'
                WHEN COUNT(c.url) > 0 THEN 'dead'
            END
            FROM resources r JOIN resource_checks c ON c.url = r.url
            WHERE r.dataset_key = datasets.key
        )
    """)
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=2500)
    ap.add_argument("--first-only", action="store_true")
    ap.add_argument("--recheck-blocked", action="store_true",
                    help="re-examine resources previously blocked or wrongly "
                         "recorded as dead because we were throttled")
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    conn = db_connect()
    conn.executescript(SCHEMA)
    todo = interleave_by_domain(
        pick_urls(conn, args.limit, args.first_only, args.recheck_blocked),
        MAX_PER_DOMAIN,
    )
    domains = len({domain_of(u) for u, _ in todo})
    print(f"{len(todo)} urls across {domains} domains "
          f"(<= {MAX_PER_DOMAIN}/domain, {DOMAIN_INTERVAL}s apart)", flush=True)

    throttle = DomainThrottle(DOMAIN_INTERVAL)
    done = 0
    verdicts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(check_one, url, fmt, throttle) for url, fmt in todo]
        for fut in as_completed(futures):
            row = fut.result()
            conn.execute(
                "INSERT OR REPLACE INTO resource_checks VALUES "
                "(:url, :status, :content_type, :size_bytes, :verdict, "
                ":columns, :checked_at)", row)
            verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1
            done += 1
            if done % 500 == 0:
                conn.commit()
                print(f"  {done}/{len(todo)}  {verdicts}", flush=True)
    conn.commit()

    aggregate_availability(conn)
    print(f"done: {done} checked  {verdicts}", flush=True)
    agg = dict(conn.execute(
        "SELECT COALESCE(availability, 'unchecked'), COUNT(*) "
        "FROM datasets GROUP BY 1").fetchall())
    print(f"dataset availability now: {agg}", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
