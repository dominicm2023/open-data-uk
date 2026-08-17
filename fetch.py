"""Look inside the files, without keeping them.

The index knows what publishers *say* about their data. Three of the findings
we want to make need to know what is actually in it: 181 of the Environment
Agency's 260 flood datasets are zip archives whose contents we cannot see,
140 of 199 sources have a literal "=Esri REST" stamped on every record
regardless of what the page really offers, and 37.9% of the index states no
format at all.

The constraint that shapes everything here: **we never copy the data.** The
site promises that, every result links to the publisher rather than to us,
and a module that quietly mirrored a few gigabytes would make it a lie. So
this reads structure and discards payload — column names, sheet names, what
is inside an archive — and stores only the description.

That constraint turns out to be a performance feature. A zip file's index
lives in its last few kilobytes, and `zipfile` only needs to seek there if
you hand it something seekable. `HttpRangeFile` makes an HTTP URL look
seekable, so listing the contents of a 2 GB archive costs about 64 KB and
one or two requests. The polite thing and the fast thing are the same thing,
which is usually a sign the design is right.

What it will not do: fetch anything behind a registration gate, follow a
link off the host the catalogue pointed at, or read more than MAX_BYTES from
any one resource.

Usage:
    python fetch.py --limit 200                 # deepen a slice
    python fetch.py --source environment_agency # a source we have a reason for
    python fetch.py --zips-only                 # just the archives
"""

from __future__ import annotations

import argparse
import csv
import os
import io
import json
import sqlite3
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from agent import HEADERS
from normalise import norm_format
from paths import connect

TIMEOUT = 45
MAX_BYTES = 3_000_000        # never read more than this from one resource
FULL_READ_MAX = 8_000_000    # only read an archive whole below this
PEEK_BYTES = 32_768          # enough for a header row and a sniff
ZIP_TAIL = 65_557            # max end-of-central-directory record + comment
WORKERS = 6

SCHEMA = """
CREATE TABLE IF NOT EXISTS resource_contents (
    vantage     TEXT,        -- which network saw this, so a gap can be explained
    url         TEXT PRIMARY KEY,
    kind        TEXT,        -- archive | table | json | unknown
    real_format TEXT,        -- what it turned out to be, normalised
    members     TEXT,        -- JSON: filenames inside an archive
    columns     TEXT,        -- JSON: column or sheet names
    rows_seen   INTEGER,     -- rows in the sample, not the file
    bytes_total INTEGER,     -- as declared by the server
    bytes_read  INTEGER,     -- what we actually transferred
    note        TEXT,
    fetched_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_contents_kind ON resource_contents(kind);

-- What each network can actually reach. Learned from outcomes rather than
-- configured, because the pattern is not guessable: SP Energy Networks and
-- Electricity North West answer a home connection and refuse the datacentre,
-- while plenty of rate-limited APIs are friendlier to the server than to a
-- laptop on a domestic line.
CREATE TABLE IF NOT EXISTS host_reach (
    host      TEXT,
    vantage   TEXT,
    ok        INTEGER DEFAULT 0,
    failed    INTEGER DEFAULT 0,
    last_seen TEXT,
    PRIMARY KEY (host, vantage)
);
"""


class HttpRangeFile(io.RawIOBase):
    """A seekable file-like view of an HTTP URL, backed by Range requests.

    Enough of the interface for `zipfile` to read a central directory. Each
    seek is free and each read is one ranged GET, so opening an archive costs
    two small requests rather than the whole file.

    Raises if the server ignores Range — a server that answers 200 to a
    ranged request is about to send the entire archive, and silently
    accepting that would be exactly the mirroring this module exists to
    avoid.
    """

    def __init__(self, session: requests.Session, url: str, size: int):
        self.session, self.url, self.size = session, url, size
        self.pos = 0
        self.read_bytes = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}
        self.pos = max(0, min(self.size, base[whence] + offset))
        return self.pos

    def tell(self) -> int:
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        if self.read_bytes + n > MAX_BYTES:
            raise IOError("would exceed the per-resource read budget")
        end = self.pos + n - 1
        r = self.session.get(self.url, headers={**HEADERS,
                                                "Range": f"bytes={self.pos}-{end}"},
                             timeout=TIMEOUT, stream=True)
        if r.status_code != 206:
            raise IOError(f"server ignored Range (HTTP {r.status_code})")
        data = r.content[:n]
        self.pos += len(data)
        self.read_bytes += len(data)
        return data


# What a file starts with, which is evidence, as against what a server says it
# is, which is a claim. The Environment Agency's download API answers HEAD with
# "Content-Length: 32, Content-Type: application/json" and then serves a
# multi-megabyte zip to the GET, so 54 flood archives were filed as tiny JSON
# documents. Sniffing costs nothing and cannot be lied to.
MAGIC = [
    (b"PK\x03\x04", "archive"),          # zip, and therefore xlsx/ods/docx too
    (b"PK\x05\x06", "archive"),          # empty zip
    (b"\x1f\x8b", "gzip"),
    (b"%PDF", "pdf"),
    (b"SQLite format 3\x00", "sqlite"),  # includes GeoPackage
    (b"\xd0\xcf\x11\xe0", "legacy-office"),
]


def _open(session: requests.Session, url: str) -> tuple[bytes, int, str]:
    """First bytes, true total size, declared content type.

    One ranged GET does the work of a HEAD and tells the truth as well: the
    Content-Range header carries the real total length even when the server's
    HEAD lied about it, and the bytes themselves say what the file is.
    """
    r = session.get(url, headers={**HEADERS, "Range": f"bytes=0-{PEEK_BYTES - 1}"},
                    timeout=TIMEOUT, stream=True, allow_redirects=True)
    head = next(r.iter_content(PEEK_BYTES), b"")
    ctype = (r.headers.get("Content-Type") or "").split(";")[0].lower()
    total = 0
    crange = r.headers.get("Content-Range") or ""
    if "/" in crange:
        try:
            total = int(crange.rsplit("/", 1)[1])
        except ValueError:
            total = 0
    if not total:
        try:
            total = int(r.headers.get("Content-Length") or 0)
        except ValueError:
            total = 0
    r.close()
    return head, total, ctype


def sniff(head: bytes) -> str | None:
    for magic, kind in MAGIC:
        if head.startswith(magic):
            return kind
    text = head.lstrip()[:1]
    if text in (b"{", b"["):
        return "json"
    return None


def read_archive(session: requests.Session, url: str, size: int) -> dict:
    """List what is inside a zip without downloading it.

    This is the whole point of the module. The Environment Agency ships flood
    risk as 181 archives; knowing whether those hold shapefiles or CSVs is
    the difference between a publishable finding and a guess, and it costs a
    few kilobytes each rather than the many gigabytes a download would.
    """
    if not size:
        return {"kind": "archive", "bytes_read": 0,
                "note": "server declared no length, cannot seek to the index"}

    # Check the server will actually seek before assuming it. Several honour
    # the opening Range and then ignore a tail request — the Environment
    # Agency's download API does exactly that — and zipfile turns the
    # resulting IOError into "File is not a zip file", which blames the
    # publisher's archive for our transport problem.
    probe_from = max(0, size - 2048)
    tail = session.get(url, headers={**HEADERS, "Range": f"bytes={probe_from}-{size - 1}"},
                       timeout=TIMEOUT, stream=True)
    seekable = tail.status_code == 206
    tail.close()

    if seekable:
        handle = HttpRangeFile(session, url, size)
        with zipfile.ZipFile(handle) as zf:
            members = [i.filename for i in zf.infolist() if not i.is_dir()]
        read = handle.read_bytes
    elif size <= FULL_READ_MAX:
        # No seeking, so the index is only reachable by reading to the end.
        # Held in memory and dropped — we still never keep the data — but it
        # costs the publisher the whole transfer, so it is capped low.
        blob = session.get(url, headers=HEADERS, timeout=TIMEOUT).content
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            members = [i.filename for i in zf.infolist() if not i.is_dir()]
        read = len(blob)
    else:
        return {"kind": "archive", "bytes_total": size, "bytes_read": 2048,
                "note": f"server will not serve a tail range and the file is "
                        f"{size / 1e6:.0f} MB — not read, since describing it "
                        f"would mean downloading all of it"}
    formats = sorted({f for f in (norm_format(m.rsplit(".", 1)[-1])
                                  for m in members if "." in m) if f})
    return {"kind": "archive", "members": members[:400],
            "real_format": ",".join(formats[:8]) or None,
            "bytes_total": size, "bytes_read": read,
            "note": f"{len(members)} files inside"
                    + ("" if seekable else " (server refused to seek, read in full)")}


def read_table(chunk: bytes, size: int) -> dict:
    """Column names and a row count from the first few kilobytes."""
    text = chunk.decode("utf-8-sig", errors="replace")
    # The last line of a truncated read is a fragment, so drop it before
    # counting: reporting half a row as a row would be a small lie that
    # compounds across 30,000 datasets.
    lines = text.splitlines()
    if len(lines) > 1 and len(chunk) >= PEEK_BYTES:
        lines = lines[:-1]
    if not lines:
        return {"kind": "table", "note": "empty"}
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]))
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    header = next(csv.reader([lines[0]], delimiter=delim), [])
    return {"kind": "table", "columns": [h.strip()[:80] for h in header][:200],
            "rows_seen": max(0, len(lines) - 1), "real_format": "CSV",
            "bytes_total": size, "bytes_read": len(chunk),
            "note": f"{len(header)} columns, sampled {len(lines) - 1} rows"}


def read_json(chunk: bytes, size: int) -> dict:
    """Top-level shape of a JSON or GeoJSON document."""
    text = chunk.decode("utf-8", errors="replace").lstrip()
    keys: list[str] = []
    fmt = "JSON"
    try:                                    # whole document, if it is small
        doc = json.loads(text)
        if isinstance(doc, dict):
            keys = list(doc)[:50]
            if doc.get("type") == "FeatureCollection":
                fmt = "GEOJSON"
                feats = doc.get("features") or []
                if feats and isinstance(feats[0], dict):
                    keys = list((feats[0].get("properties") or {}))[:200]
    except ValueError:                      # truncated: fall back to a sniff
        if '"FeatureCollection"' in text:
            fmt = "GEOJSON"
        note = "truncated, shape inferred"
        return {"kind": "json", "real_format": fmt, "bytes_total": size,
                "bytes_read": len(chunk), "note": note}
    return {"kind": "json", "real_format": fmt, "columns": keys,
            "bytes_total": size, "bytes_read": len(chunk),
            "note": f"{len(keys)} keys"}


def probe(url: str) -> dict:
    """Work out what a resource really is. Never raises."""
    row: dict = {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat()}
    session = requests.Session()
    try:
        head, size, ctype = _open(session, url)
        magic = sniff(head)
        path = urlparse(url).path.lower()

        # Magic bytes decide. Extension and content-type only get a say when
        # the file gives nothing away — a CSV looks like any other text.
        if magic == "archive":
            row |= read_archive(session, url, size)
        elif magic == "json":
            row |= read_json(head, size)
        elif magic in ("pdf", "gzip", "sqlite", "legacy-office"):
            row |= {"kind": "binary", "real_format": magic.upper(),
                    "bytes_total": size, "bytes_read": len(head),
                    "note": f"identified by magic bytes; server said "
                            f"{ctype or 'nothing'}"}
        elif path.endswith((".csv", ".tsv", ".txt")) or "csv" in ctype:
            row |= read_table(head, size)
        elif "json" in ctype or path.endswith((".json", ".geojson")):
            row |= read_json(head, size)
        else:
            row |= {"kind": "unknown", "bytes_total": size,
                    "bytes_read": len(head),
                    "note": f"content-type {ctype or 'unstated'}, "
                            f"no recognisable signature"}
    except (requests.RequestException, zipfile.BadZipFile, IOError,
            ValueError, KeyError) as exc:
        row |= {"kind": "unknown", "note": f"{type(exc).__name__}: {exc}"[:200]}
    finally:
        session.close()
    return row


def learn_reach(conn: sqlite3.Connection, rows: list[dict], vantage: str) -> None:
    """Record what this network could and could not reach.

    A resource counts as reached if we learned anything about it. Transport
    failures — refused, timed out, reset — count against the host for this
    vantage only, never against the publisher: the whole reason for keeping
    this per-network is that "we could not reach it" and "it is not there"
    are different facts, and only one of them is about them.
    """
    tally: dict[str, list[int]] = {}
    for r in rows:
        host = urlparse(r["url"]).hostname or ""
        if not host:
            continue
        note = (r.get("note") or "").lower()
        blocked = any(w in note for w in ("connection", "timeout", "timed out",
                                          "sslerror", "refused", "reset",
                                          "toomanyredirects", "proxyerror"))
        t = tally.setdefault(host, [0, 0])
        t[1 if blocked else 0] += 1
    now = datetime.now(timezone.utc).isoformat()
    for host, (ok, failed) in tally.items():
        conn.execute(
            "INSERT INTO host_reach (host, vantage, ok, failed, last_seen) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(host, vantage) DO UPDATE SET "
            "ok = ok + excluded.ok, failed = failed + excluded.failed, "
            "last_seen = excluded.last_seen", (host, vantage, ok, failed, now))
    conn.commit()


def unreachable_here(conn: sqlite3.Connection, vantage: str) -> set[str]:
    """Hosts this network has tried and consistently failed to reach.

    Three strikes and nothing to show for them. Kept deliberately loose: one
    failure is weather, and a host that has ever answered us is worth trying
    again.
    """
    return {h for (h,) in conn.execute(
        "SELECT host FROM host_reach WHERE vantage = ? AND ok = 0 AND failed >= 3",
        (vantage,))}


def reachable_elsewhere(conn: sqlite3.Connection, vantage: str) -> set[str]:
    """Hosts another network reaches that this one cannot — the work to swap."""
    return {h for (h,) in conn.execute(
        "SELECT DISTINCT r.host FROM host_reach r WHERE r.ok > 0 AND r.vantage <> ? "
        "AND EXISTS (SELECT 1 FROM host_reach m WHERE m.host = r.host "
        "            AND m.vantage = ? AND m.ok = 0 AND m.failed >= 3)",
        (vantage, vantage))}


def pick(conn: sqlite3.Connection, limit: int, source: str | None,
         zips_only: bool, title: str | None = None,
         vantage: str = "", handover: bool = False) -> list[str]:
    """Resources worth looking inside, least-known first.

    Prefers what we know least about: a resource with no recorded format
    teaches us more than one that already says CSV. Skips anything the
    checker found blocked or dead — re-fetching a 403 learns nothing and
    annoys a publisher who has already said no.
    """
    where = ["rc.verdict IN ('data', 'api')",
             "NOT EXISTS (SELECT 1 FROM resource_contents c WHERE c.url = rs.url)"]
    params: list[object] = []
    if source:
        where.append("d.source_id = ?")
        params.append(source)
    if zips_only:
        where.append("(LOWER(rs.url) LIKE '%.zip' OR rc.content_type LIKE '%zip%')")
    if title:
        # Subject-led, because the reason to look inside is usually a specific
        # question — "what is actually in the 181 flood archives" rather than
        # "deepen the index generally".
        where.append("LOWER(d.title) LIKE ?")
        params.append(f"%{title.lower()}%")
    urls = [r[0] for r in conn.execute(f"""
        SELECT rs.url
        FROM resources rs
        JOIN resource_checks rc ON rc.url = rs.url
        JOIN datasets d ON d.key = rs.dataset_key
        WHERE {' AND '.join(where)}
        GROUP BY rs.url
        ORDER BY (d.formats_norm IN ('[]', '') OR d.formats_norm IS NULL) DESC,
                 rs.url
        LIMIT ?""", params + [limit * 6])]

    # Route by what this network has learned it can reach. Hosts that have
    # refused us three times running are left for the other vantage point,
    # and --handover does the mirror image: only the work this network is
    # uniquely able to do.
    if vantage:
        blind = unreachable_here(conn, vantage)
        if handover:
            wanted = reachable_elsewhere(conn, vantage)
            urls = [u for u in urls if (urlparse(u).hostname or "") in wanted]
        else:
            urls = [u for u in urls if (urlparse(u).hostname or "") not in blind]
    return urls[:limit]


def store(conn: sqlite3.Connection, rows: list[dict]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO resource_contents "
        "(url, kind, real_format, members, columns, rows_seen, bytes_total, "
        " bytes_read, note, fetched_at, vantage) VALUES "
        "(:url, :kind, :real_format, :members, :columns, :rows_seen, "
        " :bytes_total, :bytes_read, :note, :fetched_at, :vantage)",
        [{"members": None, "columns": None, "rows_seen": None,
          "bytes_total": None, "bytes_read": None, "real_format": None,
          "note": None, "vantage": None, **r,
          "members": json.dumps(r["members"]) if r.get("members") else None,
          "columns": json.dumps(r["columns"]) if r.get("columns") else None}
         for r in rows])
    conn.commit()


def export_rows(conn: sqlite3.Connection, vantage: str, path: Path) -> int:
    """Everything this network learned, for merging into the other's database.

    The two vantage points necessarily run against different copies, so
    handover only works if each can tell the other what it found and what it
    could not reach. Small enough to move by scp; JSON so it can be read
    before it is trusted.
    """
    contents = [dict(zip([c[0] for c in cur.description], row))
                for cur in [conn.execute(
                    "SELECT * FROM resource_contents WHERE vantage = ?", (vantage,))]
                for row in cur]
    reach = [dict(zip([c[0] for c in cur.description], row))
             for cur in [conn.execute(
                 "SELECT * FROM host_reach WHERE vantage = ?", (vantage,))]
             for row in cur]
    path.write_text(json.dumps({"vantage": vantage, "contents": contents,
                                "reach": reach}, indent=1), encoding="utf-8")
    return len(contents)


def import_rows(conn: sqlite3.Connection, path: Path) -> tuple[int, int]:
    """Merge another network's findings. Its reach counts stay under its own
    vantage, so neither side inherits the other's blind spots as its own."""
    data = json.loads(path.read_text(encoding="utf-8"))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(resource_contents)")}
    rows = [{k: v for k, v in r.items() if k in cols} for r in data["contents"]]
    for r in rows:
        keys = ", ".join(r)
        conn.execute(f"INSERT OR REPLACE INTO resource_contents ({keys}) "
                     f"VALUES ({', '.join(':' + k for k in r)})", r)
    for r in data["reach"]:
        conn.execute(
            "INSERT INTO host_reach (host, vantage, ok, failed, last_seen) "
            "VALUES (:host, :vantage, :ok, :failed, :last_seen) "
            "ON CONFLICT(host, vantage) DO UPDATE SET ok = excluded.ok, "
            "failed = excluded.failed, last_seen = excluded.last_seen", r)
    conn.commit()
    return len(rows), len(data["reach"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--source", help="only this source id")
    ap.add_argument("--zips-only", action="store_true")
    ap.add_argument("--title", help="only datasets whose title contains this")
    ap.add_argument("--workers", type=int, default=WORKERS)
    ap.add_argument("--vantage", default=os.environ.get("FETCH_VANTAGE")
                    or ("vps" if Path("/etc/caddy").exists() else "local"),
                    help="which network this is running on")
    ap.add_argument("--export", help="write this vantage's findings to a file")
    ap.add_argument("--import", dest="import_", help="merge another vantage's file")
    ap.add_argument("--handover", action="store_true",
                    help="only hosts the other vantage point reaches and this "
                         "one cannot")
    args = ap.parse_args()

    conn = connect()
    conn.executescript(SCHEMA)
    # The table predates the vantage column, and CREATE TABLE IF NOT EXISTS
    # will not add it to an existing one.
    if "vantage" not in {r[1] for r in conn.execute(
            "PRAGMA table_info(resource_contents)")}:
        conn.execute("ALTER TABLE resource_contents ADD COLUMN vantage TEXT")
        conn.commit()
    if args.import_:
        n, hosts = import_rows(conn, Path(args.import_))
        print(f"merged {n:,} descriptions and {hosts} host-reach rows")
        conn.close()
        return 0

    urls = pick(conn, args.limit, args.source, args.zips_only, args.title,
                args.vantage, args.handover)
    if not urls:
        print("nothing left to look inside for that selection")
        return 0
    print(f"looking inside {len(urls)} resources\n")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(probe, urls))
    for r in rows:
        r["vantage"] = args.vantage
    store(conn, rows)
    learn_reach(conn, rows, args.vantage)

    kinds: dict[str, int] = {}
    read = 0
    for r in rows:
        kinds[r.get("kind") or "?"] = kinds.get(r.get("kind") or "?", 0) + 1
        read += r.get("bytes_read") or 0
    declared = sum(r.get("bytes_total") or 0 for r in rows)
    for kind, n in sorted(kinds.items(), key=lambda k: -k[1]):
        print(f"   {kind:9} {n:>5}")
    print(f"\nread {read / 1e6:.1f} MB to describe {declared / 1e6:.1f} MB "
          f"of files — we keep the description, never the data")
    if args.export:
        n = export_rows(conn, args.vantage, Path(args.export))
        print(f"exported {n:,} descriptions from {args.vantage} "
              f"to {args.export}, for the other vantage point to merge")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
