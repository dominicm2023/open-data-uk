"""Fetch the organogram CSVs named in the manifest.

Polite by construction: one request per host at a time, a fixed interval
between them, and everything cached on disk by URL hash so a re-run costs
nothing. These are other people's servers and most of them are small.

Files land in raw/ (gitignored) and a receipt is written per URL recording
status, size and content type, so the parse step can reason about what it
has without re-reading every file.

Usage:
    python analysis/organograms/02_fetch.py            # fetch what's missing
    python analysis/organograms/02_fetch.py --limit 50 # a taste first
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
from agent import USER_AGENT  # noqa: E402

HERE = Path(__file__).parent
RAW = HERE / "raw"
RECEIPTS = HERE / "receipts.jsonl"

DOMAIN_INTERVAL = 1.0     # seconds between requests to the same host
WORKERS = 8
TIMEOUT = 45
MAX_BYTES = 40 * 1024 * 1024   # an organogram is never this big


class Throttle:
    """One request per host at a time, spaced. Copied in spirit from
    checker.py, which learned this the hard way."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._next: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(self._next.get(host, now), now)
            self._next[host] = slot + self.interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def cache_path(url: str) -> Path:
    return RAW / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".csv")


def fetch(row: dict, throttle: Throttle, session_local) -> dict:
    url = row["url"]
    path = cache_path(url)
    if path.exists() and path.stat().st_size > 0:
        return {"url": url, "status": "cached", "bytes": path.stat().st_size}

    session = getattr(session_local, "s", None)
    if session is None:
        session = session_local.s = requests.Session()
        session.headers["User-Agent"] = USER_AGENT

    throttle.wait(urlparse(url).hostname or "")
    try:
        r = session.get(url, timeout=TIMEOUT, stream=True)
        if r.status_code != 200:
            r.close()
            return {"url": url, "status": f"http {r.status_code}", "bytes": 0}
        chunks, total = [], 0
        for chunk in r.iter_content(65536):
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_BYTES:
                r.close()
                return {"url": url, "status": "too big", "bytes": total}
        r.close()
        path.write_bytes(b"".join(chunks))
        return {"url": url, "status": "ok", "bytes": total,
                "content_type": r.headers.get("content-type", "")[:80]}
    except Exception as exc:  # noqa: BLE001 - one bad host must not stop the run
        return {"url": url, "status": f"{type(exc).__name__}", "bytes": 0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(HERE / "manifest.csv", encoding="utf-8")))
    if args.limit:
        rows = rows[:args.limit]

    # Interleave hosts so eight workers aren't all queued behind one server.
    by_host: dict[str, list[dict]] = {}
    for row in rows:
        by_host.setdefault(urlparse(row["url"]).hostname or "", []).append(row)
    ordered, pools = [], list(by_host.values())
    while pools:
        for pool in list(pools):
            ordered.append(pool.pop(0))
            if not pool:
                pools.remove(pool)

    print(f"{len(ordered):,} files across {len(by_host):,} hosts, "
          f"{WORKERS} workers, {DOMAIN_INTERVAL}s apart per host")
    throttle = Throttle(DOMAIN_INTERVAL)
    session_local = threading.local()
    done = 0
    with open(RECEIPTS, "a", encoding="utf-8") as receipts:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for result in pool.map(
                    lambda r: fetch(r, throttle, session_local), ordered):
                receipts.write(json.dumps(result) + "\n")
                done += 1
                if done % 250 == 0:
                    print(f"   {done:,}/{len(ordered):,}", flush=True)

    from collections import Counter
    states = Counter(json.loads(l)["status"].split()[0]
                     for l in open(RECEIPTS, encoding="utf-8"))
    print("\n" + ", ".join(f"{k}: {v:,}" for k, v in states.most_common()))
    total = sum(p.stat().st_size for p in RAW.glob("*.csv"))
    print(f"{len(list(RAW.glob('*.csv'))):,} files on disk, "
          f"{total / 1e6:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
