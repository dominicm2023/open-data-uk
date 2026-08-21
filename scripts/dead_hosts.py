"""Find the hostnames the UK's open data catalogues still point at, but which
no longer answer.

The national catalogue keeps its records long after the servers behind them
go. Only an index that spans every portal can see this: data.gov.uk lists a
council's dataset, the council's own portal is gone, and each catalogue on
its own looks perfectly healthy.

Being right here matters more than being interesting. "This organisation's
data has vanished" is a specific accusation, and there are several ways to
reach it wrongly:

  * a host that refuses OUR checker but serves everyone else
  * a host that is merely slow, or was down for an hour
  * a firewall that blocks the datacentre our checker runs in, but not the
    public
  * an expired TLS certificate, which is a real fault but a different one
    from "the server is gone"

So a host is only reported when it fails from **two** vantage points (this
machine and, with --vps, the server), and the failure is classified by what
actually happened rather than lumped into "dead":

    no-dns      the name doesn't resolve — the record is gone
    no-answer   the name resolves, nothing listens
    tls-broken  a server answers but its certificate is unusable
    alive       serves fine, so our stored failure is OUR artefact

Only the first three are reported. `alive` hosts are counted and named in the
output precisely because they are the ones that would have produced a false
claim.

The `alive` finding cuts both ways, so this also repairs. A host we recorded
as unreachable but which answers fine means we are showing its datasets to
users as broken. Those stored checks are wrong, and `--repair` deletes them
so the nightly checker re-verifies from scratch — deleting is safe because a
check result is a measurement we can always take again, and leaving it is
not, because it is a false statement about someone's data.

Usage:
    python scripts/dead_hosts.py               # probe, write dead_hosts.json
    python scripts/dead_hosts.py --min 5       # include smaller hosts
    python scripts/dead_hosts.py --repair      # also clear provably-wrong checks
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import HEADERS  # noqa: E402
from paths import connect  # noqa: E402

OUT = Path(__file__).parent.parent / "dead_hosts.json"
TIMEOUT = 20
WORKERS = 8          # polite: one request per host, and only to the root


def probe(host: str) -> dict:
    """Classify a hostname by what actually happens when you try it."""
    try:
        socket.gethostbyname(host)
    except OSError:
        return {"host": host, "state": "no-dns", "detail": "does not resolve"}

    last = ""
    for scheme in ("https", "http"):
        try:
            r = requests.get(f"{scheme}://{host}/", headers=HEADERS,
                             timeout=TIMEOUT, allow_redirects=True)
            return {"host": host, "state": "alive",
                    "detail": f"{scheme} {r.status_code}"}
        except requests.exceptions.SSLError as exc:
            last = f"TLS: {type(exc).__name__}"
        except requests.exceptions.RequestException as exc:
            last = type(exc).__name__
    if last.startswith("TLS"):
        return {"host": host, "state": "tls-broken", "detail": last}
    return {"host": host, "state": "no-answer", "detail": last}


def candidates(conn, minimum: int) -> dict[str, dict]:
    """Hosts our checker could not connect to at all, with who they belong to."""
    rows = conn.execute("""
        SELECT rs.url, d.publisher, d.source_id
        FROM resources rs
        JOIN resource_checks rc ON rc.url = rs.url
        JOIN datasets d ON d.key = rs.dataset_key
        WHERE rc.verdict IN ('dead', 'unreachable') AND rc.status = 0""").fetchall()
    hosts: dict[str, dict] = {}
    for url, pub, src in rows:
        host = urlparse(url).hostname
        # A hostname of "https" means we stored a malformed URL — that is our
        # bug to fix, not a publisher's dead server, so it must never be
        # reported as one.
        if not host or "." not in host:
            continue
        h = hosts.setdefault(host, {"resources": 0, "publishers": set(),
                                    "sources": set()})
        h["resources"] += 1
        if pub:
            h["publishers"].add(pub)
        h["sources"].add(src)
    return {k: v for k, v in hosts.items() if v["resources"] >= minimum}


def repair(conn, alive_hosts: list[str]) -> int:
    """Forget the connection failures we recorded against hosts that work.

    Only rows with status = 0 are touched: a genuine 404 from one of these
    hosts is still a genuine 404, and this is not licence to erase real
    findings. Availability is recomputed straight away, so nothing is left
    claiming 'dead' on the strength of a check that no longer exists.
    """
    from checker import aggregate_availability

    n = 0
    for host in alive_hosts:
        cur = conn.execute(
            "DELETE FROM resource_checks WHERE status = 0 AND url IN "
            "(SELECT url FROM resources WHERE url LIKE ? OR url LIKE ?)",
            (f"http://{host}/%", f"https://{host}/%"))
        n += cur.rowcount
    conn.commit()
    aggregate_availability(conn)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min", type=int, default=10,
                    help="minimum unreachable resources to bother probing")
    ap.add_argument("--repair", action="store_true",
                    help="delete stored checks for hosts that answer fine, so "
                         "the checker re-verifies them")
    args = ap.parse_args()

    conn = connect()
    hosts = candidates(conn, args.min)
    print(f"probing {len(hosts)} hostnames our checker could not connect to\n")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(probe, hosts))

    out, alive = [], []
    for r in results:
        meta = hosts[r["host"]]
        r["resources"] = meta["resources"]
        r["publishers"] = sorted(meta["publishers"])
        r["sources"] = sorted(meta["sources"])
        (alive if r["state"] == "alive" else out).append(r)

    out.sort(key=lambda r: -r["resources"])
    for r in out:
        print(f"   {r['state']:11} {r['host'][:42]:42} {r['resources']:>5} "
              f"resources  {len(r['publishers'])} publisher(s)")
    if alive:
        print(f"\n{len(alive)} host(s) answer fine — our stored failure is our own "
              f"artefact, not theirs, and they are excluded:")
        for r in alive:
            print(f"   {r['host'][:42]:42} {r['detail']}")
        if args.repair:
            cleared = repair(conn, [r["host"] for r in alive])
            print(f"\ncleared {cleared:,} wrong checks — the next checker run "
                  f"re-verifies them from scratch")
        else:
            print("   (run with --repair to clear their wrong 'dead' verdicts)")

    conn.close()
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    total = sum(r["resources"] for r in out)
    pubs = {p for r in out for p in r["publishers"]}
    print(f"\n{len(out)} unreachable hosts, {total:,} resources, "
          f"{len(pubs)} publishers affected — wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
