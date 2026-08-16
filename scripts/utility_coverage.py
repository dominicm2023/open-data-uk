"""Probe the utilities, network operators and transport bodies for portals.

Councils have a register; infrastructure doesn't, so utilities.yaml is a
curated candidate list and this decides which of it is real. For each
organisation it tries every catalogue API we can already harvest against
every candidate domain, and records what actually answered.

Nothing here is asserted. A candidate domain is a guess; a row in the output
is a measurement. That distinction matters more than usual in this sector,
because a lot of "open data" from utilities turns out to be a CSV linked from
a corporate page with no catalogue behind it at all — findable by a human,
invisible to a harvester.

DNS-resolves first so we don't fire HTTP at hundreds of names that don't
exist, and never touches anything marked `note: key`: harvesting anonymously
past a registration gate would be helping ourselves to something the
publisher chose to meter.

Usage:
    python scripts/utility_coverage.py               # probe and report
    python scripts/utility_coverage.py --sector Water
"""

from __future__ import annotations

import argparse
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).parent.parent
OUT = ROOT / "UTILITIES_COVERAGE.md"
UA = {"User-Agent": "uk-open-data-index/0.2 (platform discovery; "
                    "+https://open-data.org.uk/about)"}
TIMEOUT = 15

# Every catalogue shape we have a harvester for. Ordered cheapest-first;
# the first that answers wins, so a portal offering two APIs is recorded as
# the one we would actually harvest it with.
PROBES = [
    ("ods", "/api/explore/v2.1/catalog/datasets?limit=1",
     lambda j: j.get("total_count")),
    ("ckan", "/api/3/action/package_search?rows=1",
     lambda j: j["result"]["count"]),
    ("ckan", "/api/action/package_search?rows=1",
     lambda j: j["result"]["count"]),
    ("dcat", "/data.json", lambda j: len(j.get("dataset") or [])),
    ("dcat", "/api/feed/dcat-us/1.1.json", lambda j: len(j.get("dataset") or [])),
    ("geonode", "/api/v2/layers/?page_size=1", lambda j: j.get("total")),
]


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return True
    except OSError:
        return False


def probe(host: str) -> tuple[str, str, int] | None:
    """(platform, api_url, dataset_count) for the first API that answers."""
    base = f"https://{host}"
    for kind, path, count in PROBES:
        try:
            r = requests.get(base + path, headers=UA, timeout=TIMEOUT)
            if not r.ok or "json" not in r.headers.get("content-type", ""):
                continue
            n = count(r.json())
            if isinstance(n, int) and n > 0:
                return (kind, base + path.split("?")[0], n)
        except Exception:  # noqa: BLE001 - a candidate that errors is a no
            continue
    return None


def serves_a_page(host: str) -> bool:
    """Does anything actually answer here?

    DNS resolving is not evidence: *.opendatasoft.com resolves for every
    name, so a guessed tenant looks alive until the TLS handshake fails on a
    certificate that was never issued for it. Counting those as "a site
    exists" turned 28 dead guesses into apparent near-misses.
    """
    try:
        r = requests.get(f"https://{host}/", headers=UA, timeout=TIMEOUT,
                         allow_redirects=True)
        return r.status_code == 200
    except Exception:  # noqa: BLE001 - TLS failure, refused, timeout: nothing there
        return False


def check(entry: dict) -> dict:
    out = {**entry, "platform": None, "api": None, "datasets": 0,
           "state": "none", "live_domains": []}
    if entry.get("note") == "key":
        out["state"] = "gated"
        return out

    # Plenty of these serve only on www — streamwaterdata.co.uk fails TLS
    # bare and answers fine with the prefix. Cheaper to try both than to
    # hand-maintain the variants in the yaml.
    wanted = []
    for h in entry["candidates"]:
        wanted += [h] if h.startswith("www.") else [h, "www." + h]
    for host in [h for h in dict.fromkeys(wanted) if resolves(h)]:
        if hit := probe(host):
            kind, api, n = hit
            out.update(platform=kind, api=api, datasets=n, state="portal",
                       domain=host)
            return out
        if serves_a_page(host):
            out["live_domains"].append(host)
    out["state"] = "site" if out["live_domains"] else "none"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sector", help="probe one sector only")
    args = ap.parse_args()

    entries = yaml.safe_load(open(ROOT / "utilities.yaml", encoding="utf-8"))["utilities"]
    if args.sector:
        entries = [e for e in entries if e["sector"].lower() == args.sector.lower()]
    print(f"probing {len(entries)} organisations "
          f"({sum(len(e['candidates']) for e in entries)} candidate domains) ...\n")

    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(check, entries))

    known = {s["web"].split("//")[-1].rstrip("/")
             for s in yaml.safe_load(
                 open(ROOT / "sources.yaml", encoding="utf-8"))["sources"]}
    for r in rows:
        if r.get("domain") in known:
            r["state"] = "harvested"

    order = {"harvested": 0, "portal": 1, "site": 2, "gated": 3, "none": 4}
    rows.sort(key=lambda r: (r["sector"], order[r["state"]], r["name"]))

    mark = {"harvested": "✅", "portal": "🟢", "site": "🌐",
            "gated": "🔑", "none": "⬜"}
    # The report is UTF-8; a Windows console is not. Keep the emoji in the
    # file and print something every terminal can render.
    plain = {"harvested": "[have]", "portal": "[NEW] ", "site": "[site]",
             "gated": "[key] ", "none": "[  -  ]"}
    tally = {k: sum(1 for r in rows if r["state"] == k) for k in order}
    found = [r for r in rows if r["state"] == "portal"]

    lines = [
        "# Utilities, transport and roads — coverage",
        "",
        "The organisations that run the UK's physical infrastructure: energy "
        "networks, water companies, road and rail operators. Unlike councils "
        "these have no register, so [`utilities.yaml`](utilities.yaml) is a "
        "curated candidate list and this file is what probing it actually "
        "found. Generated by "
        "[`scripts/utility_coverage.py`](scripts/utility_coverage.py).",
        "",
        f"| | Count |", "|---|---:|",
        f"| ✅ already harvested | {tally['harvested']} |",
        f"| 🟢 portal found, not yet harvested | {tally['portal']} |",
        f"| 🌐 site exists, no catalogue API | {tally['site']} |",
        f"| 🔑 needs registration or an API key | {tally['gated']} |",
        f"| ⬜ nothing resolved | {tally['none']} |",
        "",
        "🌐 is the interesting category and the reason this sector is harder "
        "than local government: the organisation publishes data, but as files "
        "linked from a corporate page rather than through a catalogue. A "
        "person can find it; a harvester cannot. Those need either a bespoke "
        "adapter each or a human to add the files by hand.",
        "",
        "🔑 entries are listed for completeness and deliberately not probed. "
        "Harvesting anonymously past a registration gate would be helping "
        "ourselves to something the publisher chose to meter.",
        "",
        "| Organisation | Sector | | Platform | Datasets | Endpoint |",
        "|---|---|---|---|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['sector']} | {mark[r['state']]} | "
            f"{r['platform'] or '—'} | {r['datasets'] or ''} | "
            f"{'`' + r['api'] + '`' if r['api'] else ''} |")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    for r in rows:
        print(f"  {plain[r['state']]} {r['name'][:44]:44} "
              f"{(r['platform'] or ''):8} {r['datasets'] or '':>7}")
    print(f"\n{tally['harvested']} harvested · {tally['portal']} new portals · "
          f"{tally['site']} sites without a catalogue · {tally['gated']} gated · "
          f"{tally['none']} nothing")
    if found:
        print("\n=== proposed sources.yaml entries (verify before merging) ===")
        for r in found:
            slug = r["name"].lower().replace(" ", "_")[:24]
            print(f"  - id: {slug}\n"
                  f"    name: {r['name']}\n"
                  f"    type: {r['platform']}\n"
                  f"    api: {r['api']}\n"
                  f"    web: https://{r['domain']}\n")
    print(f"wrote {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
