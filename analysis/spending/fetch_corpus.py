"""Fetch the selected spending CSVs into raw\\, politely, with a manifest.

Politeness rules (project-wide, non-negotiable):
  - HEADERS imported from agent.py at repo root
  - at most 2 requests/second per host (0.5s spacing, enforced per host)
  - 60s timeout; never retry a 403/429 more than once
  - GET with stream (no HEAD, no Range — servers lie), per-file cap 150 MB,
    total-download cap 4 GB

Files are named by sha1(url). Manifest maps url -> record. Resumable: URLs
already in the manifest are not refetched.
"""
import hashlib
import json
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
sys.path.insert(0, str(ROOT))
from agent import HEADERS  # noqa: E402

PER_FILE_CAP = 150 * 1024 * 1024
TOTAL_CAP = 4 * 1024 * 1024 * 1024
HOST_SPACING = 0.5  # 2 req/s per host
TIMEOUT = 60
WORKERS_PER_HOST = 1  # spacing is per host, so one worker per host

manifest_lock = threading.Lock()
total_lock = threading.Lock()
total_bytes = 0
manifest = {}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sniff(first_bytes: bytes) -> str:
    if first_bytes.startswith(b"PK\x03\x04"):
        return "xlsx-zip"
    if first_bytes.startswith(b"\xd0\xcf\x11\xe0"):
        return "xls-ole"
    if first_bytes.startswith(b"%PDF"):
        return "pdf"
    head = first_bytes.lstrip()[:200].lower()
    if head.startswith(b"<!doctype") or head.startswith(b"<html") or head.startswith(b"<?xml"):
        return "html-or-xml"
    if first_bytes.lstrip()[:1] == b"<":
        return "html-or-xml"
    return "text"


def fetch_one(session, url, meta):
    global total_bytes
    rec = {"dataset_key": meta["dataset_key"], "publisher": meta["publisher"],
           "title": meta["title"], "file": None, "bytes": 0,
           "http_status": None, "fetched_at": now(), "sniff": None, "error": None}
    with total_lock:
        if total_bytes >= TOTAL_CAP:
            rec["error"] = "total-cap-reached"
            return rec
    name = hashlib.sha1(url.encode()).hexdigest()
    dest = RAW / (name + ".bin")
    tries = 0
    while True:
        tries += 1
        try:
            r = session.get(url, headers=HEADERS, timeout=TIMEOUT, stream=True,
                            allow_redirects=True)
        except requests.RequestException as e:
            rec["error"] = f"request-error: {type(e).__name__}"
            return rec
        rec["http_status"] = r.status_code
        if r.status_code in (403, 429) and tries == 1:
            r.close()
            time.sleep(5)
            continue
        if r.status_code != 200:
            r.close()
            rec["error"] = f"http-{r.status_code}"
            return rec
        size = 0
        first = b""
        try:
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    if not chunk:
                        continue
                    if not first:
                        first = chunk[:512]
                    size += len(chunk)
                    if size > PER_FILE_CAP:
                        rec["error"] = "over-150MB-skipped"
                        break
                    f.write(chunk)
        except requests.RequestException as e:
            rec["error"] = f"stream-error: {type(e).__name__}"
            dest.unlink(missing_ok=True)
            return rec
        finally:
            r.close()
        if rec["error"] == "over-150MB-skipped":
            dest.unlink(missing_ok=True)
            return rec
        rec["file"] = dest.name
        rec["bytes"] = size
        rec["sniff"] = sniff(first)
        with total_lock:
            total_bytes += size
        return rec


def host_worker(host, q):
    session = requests.Session()
    while True:
        item = q.get()
        if item is None:
            q.task_done()
            return
        url, meta = item
        t0 = time.monotonic()
        rec = fetch_one(session, url, meta)
        with manifest_lock:
            manifest[url] = rec
            if len(manifest) % 200 == 0:
                save()
                print(f"progress: {len(manifest)} fetched, "
                      f"{total_bytes/1e6:.0f} MB", flush=True)
        q.task_done()
        elapsed = time.monotonic() - t0
        if elapsed < HOST_SPACING:
            time.sleep(HOST_SPACING - elapsed)


def save():
    tmp = HERE / "manifest.json.tmp"
    tmp.write_text(json.dumps(manifest, indent=0), encoding="utf-8")
    tmp.replace(HERE / "manifest.json")


def main():
    RAW.mkdir(exist_ok=True)
    sel = json.loads((HERE / "selection.json").read_text(encoding="utf-8"))
    mpath = HERE / "manifest.json"
    if mpath.exists():
        manifest.update(json.loads(mpath.read_text(encoding="utf-8")))
        global total_bytes
        total_bytes = sum(r.get("bytes") or 0 for r in manifest.values())
        print(f"resuming: {len(manifest)} already in manifest, "
              f"{total_bytes/1e6:.0f} MB", flush=True)

    todo = [(u, m) for u, m in sel["selection"].items()
            if m["fetch"] and u not in manifest]
    print(f"to fetch now: {len(todo)}", flush=True)

    by_host = defaultdict(list)
    for u, m in todo:
        by_host[urlparse(u).netloc].append((u, m))

    threads = []
    for host, items in by_host.items():
        q = Queue()
        for it in items:
            q.put(it)
        q.put(None)
        t = threading.Thread(target=host_worker, args=(host, q), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    save()
    ok = sum(1 for r in manifest.values() if r.get("file"))
    print(f"done: {len(manifest)} attempted, {ok} saved, "
          f"{total_bytes/1e6:.0f} MB total", flush=True)


if __name__ == "__main__":
    main()
