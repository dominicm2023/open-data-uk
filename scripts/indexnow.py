"""Tell search engines which pages changed, the moment they change.

A sitemap says "here are 60,000 URLs, some of them are different now, good
luck". IndexNow says "these 213 changed tonight". Bing, and through it
DuckDuckGo and Ecosia, plus Yandex, Seznam and Naver, all accept it; Google
does not participate.

The hard part is knowing what actually changed. `harvested_at` moves on every
upsert whether or not anything differed, so it can't answer the question —
this keeps a fingerprint of what each page *displays* and submits only the
pages whose fingerprint moved. Re-announcing unchanged URLs is how a site
gets its submissions ignored.

The key is public by design: IndexNow verifies ownership by fetching it back
from the site root, so it is in the repo deliberately, not by accident.

Usage:
    python scripts/indexnow.py --dry-run       # what would go, and why
    python scripts/indexnow.py                 # submit and record
    python scripts/indexnow.py --reset         # forget state, re-bootstrap
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from paths import connect as db_connect  # noqa: E402

ROOT = Path(__file__).parent.parent
SITE = "https://open-data.org.uk"
HOST = "open-data.org.uk"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH = 10_000        # IndexNow's documented ceiling per request
TIMEOUT = 30

# Pages that genuinely change whenever any dataset does. Cheap to include,
# and they are the entry points to everything else.
HUB_PAGES = ["/", "/publishers", "/topics", "/who-publishes"]

# The same filter the sitemap uses, so we never announce a URL we've asked
# not to be indexed.
INDEXABLE = """
  FROM datasets d
  WHERE NOT EXISTS (SELECT 1 FROM duplicates x WHERE x.key = d.key)
    AND NOT EXISTS (SELECT 1 FROM retired r WHERE r.key = d.key)
    AND NOT (LENGTH(TRIM(COALESCE(d.description,''))) < 40
             AND COALESCE(d.resource_count,0) = 0
             AND COALESCE(d.tags,'[]') IN ('[]','')
             AND COALESCE(d.formats_norm,'[]') IN ('[]',''))
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS indexnow (
    key          TEXT PRIMARY KEY,
    fingerprint  TEXT NOT NULL,
    submitted_at TEXT
);
"""


def find_key() -> tuple[str, str]:
    """The key, and the URL search engines will fetch to verify it."""
    files = sorted(ROOT.glob("web/*.txt"))
    for f in files:
        text = f.read_text(encoding="utf-8").strip()
        if f.stem == text and len(text) >= 8:
            return text, f"{SITE}/{f.name}"
    raise SystemExit(
        "No IndexNow key file found. It must live at web/<key>.txt and "
        "contain exactly that key.")


def fingerprint(row: sqlite3.Row) -> str:
    """A hash of everything the dataset page shows a reader.

    Deliberately not the whole row: `harvested_at` moves nightly regardless,
    and announcing a page because we re-read it — rather than because it
    changed — is precisely the noise IndexNow asks us not to make.
    """
    parts = [str(row[c] or "") for c in
             ("title", "description", "publisher", "license_norm", "modified",
              "formats_norm", "resource_count", "availability")]
    return hashlib.sha1("␟".join(parts).encode("utf-8")).hexdigest()[:16]


def dataset_url(key: str) -> str:
    import urllib.parse
    return f"{SITE}/dataset?key=" + urllib.parse.quote(key, safe="")


def submit(urls: list[str], key: str, key_location: str, dry: bool) -> bool:
    if dry:
        return True
    body = {"host": HOST, "key": key, "keyLocation": key_location,
            "urlList": urls}
    r = requests.post(ENDPOINT, json=body, timeout=TIMEOUT,
                      headers={"Content-Type": "application/json; charset=utf-8"})
    # 200 accepted, 202 accepted-pending-key-validation. Anything else is
    # worth printing but never worth failing the nightly refresh over.
    ok = r.status_code in (200, 202)
    print(f"  {ENDPOINT} -> HTTP {r.status_code}"
          f"{'' if ok else ' ' + r.text[:200]}")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="show what would be submitted, send nothing")
    ap.add_argument("--limit", type=int, default=BATCH)
    ap.add_argument("--reset", action="store_true",
                    help="drop recorded fingerprints and re-bootstrap")
    args = ap.parse_args()

    key, key_location = find_key()
    conn = db_connect()
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if args.reset:
        conn.execute("DELETE FROM indexnow")
        conn.commit()

    known = {r["key"]: r["fingerprint"]
             for r in conn.execute("SELECT key, fingerprint FROM indexnow")}
    current = {r["key"]: fingerprint(r) for r in conn.execute(
        "SELECT d.key, d.title, d.description, d.publisher, d.license_norm, "
        "d.modified, d.formats_norm, d.resource_count, d.availability "
        + INDEXABLE)}

    new = [k for k in current if k not in known]
    changed = [k for k, f in current.items() if k in known and known[k] != f]
    gone = [k for k in known if k not in current]

    print(f"{len(current):,} indexable datasets")
    print(f"  new     : {len(new):,}")
    print(f"  changed : {len(changed):,}")
    print(f"  no longer indexable: {len(gone):,} (nothing to announce)")

    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # First run: record what is there without announcing 60,000 URLs. The
    # sitemap already covers the back catalogue; IndexNow is for deltas.
    if not known:
        print("\nfirst run — recording fingerprints, submitting nothing")
        if not args.dry_run:
            conn.executemany(
                "INSERT OR REPLACE INTO indexnow VALUES (?, ?, ?)",
                [(k, f, stamp) for k, f in current.items()])
            conn.commit()
        conn.close()
        return 0

    to_send = new + changed
    if not to_send:
        print("\nnothing changed since the last run")
        conn.close()
        return 0

    # The hub pages ride along in the same request, so they spend part of
    # the budget. Capping datasets at the full limit and appending the hubs
    # afterwards sent 10,004 URLs the first time three nights of backlog
    # accumulated, and IndexNow rejected the entire request — its 400 said,
    # exactly: "You have added 4 more Urls."
    cap = args.limit - len(HUB_PAGES)
    if len(to_send) > cap:
        print(f"\n{len(to_send):,} changes exceeds the {cap:,} cap — "
              "submitting the first batch, the rest go tomorrow")
        to_send = to_send[:cap]

    urls = [dataset_url(k) for k in to_send] + [SITE + p for p in HUB_PAGES]
    print(f"\nsubmitting {len(urls):,} URLs"
          f"{' (dry run)' if args.dry_run else ''}")
    for u in urls[:5]:
        print(f"  {u[:110]}")
    if len(urls) > 5:
        print(f"  ... and {len(urls) - 5:,} more")

    if submit(urls, key, key_location, args.dry_run) and not args.dry_run:
        conn.executemany("INSERT OR REPLACE INTO indexnow VALUES (?, ?, ?)",
                         [(k, current[k], stamp) for k in to_send])
        conn.commit()
        print(f"recorded {len(to_send):,} fingerprints")
    conn.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        # Never fail the nightly refresh over a search-engine ping.
        print(f"indexnow: {type(exc).__name__}: {exc}")
        sys.exit(0)
