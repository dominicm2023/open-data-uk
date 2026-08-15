"""Discover open-data portals we aren't harvesting yet, deterministically.

Two free signals, no guessing and no LLM:

1. **Our own index.** Resource URLs point back at the portals datasets came
   from, so unharvested portal domains are already sitting in the database.
2. **Naming conventions.** Councils cluster on a handful of platforms with
   predictable hostnames (data.<x>.gov.uk, <x>.opendata.arcgis.com, ...),
   so candidates can be generated from the authority names we already hold.

Every candidate is DNS-resolved first (cheap, no traffic to anyone) and only
resolvable hosts get an HTTP probe, so we don't spray requests at hundreds
of nonexistent names.

Output is ready-to-paste sources.yaml entries for anything confirmed. It
never edits sources.yaml itself — proposals go through review and
scripts/validate_sources.py like any other contribution.

Usage:
    python scripts/discover_sources.py                 # both signals
    python scripts/discover_sources.py --from-index    # only signal 1
    python scripts/discover_sources.py --from-names    # only signal 2
"""

from __future__ import annotations

import argparse
import collections
import socket
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from geo import _ORG_WORDS  # noqa: E402  (reuse: same "strip the org words" job)
from paths import connect as db_connect  # noqa: E402

ROOT = Path(__file__).parent.parent
UA = {"User-Agent": "uk-open-data-index/0.2 (source discovery; +https://open-data.org.uk/about)"}
TIMEOUT = 8   # a real portal answers fast; anything slower isn't worth the wait

# Hostname shapes councils and agencies actually use
HOST_PATTERNS = (
    "data.{s}.gov.uk",
    "opendata.{s}.gov.uk",
    "{s}.opendata.arcgis.com",
    "opendata-{s}.opendata.arcgis.com",
    "data-{s}.opendata.arcgis.com",
    "{s}.hub.arcgis.com",
)

# (kind, path, how to count datasets in the response)
API_PROBES = (
    ("dcat", "/api/feed/dcat-us/1.1.json", lambda j: len(j.get("dataset") or [])),
    ("ckan", "/api/3/action/package_search?rows=1", lambda j: j["result"]["count"]),
    ("ckan", "/api/action/package_search?rows=1", lambda j: j["result"]["count"]),
)


def known_domains() -> set[str]:
    src = yaml.safe_load(open(ROOT / "sources.yaml", encoding="utf-8"))["sources"]
    out = set()
    for s in src:
        for field in ("web", "api"):
            out.add(urllib.parse.urlparse(s[field]).netloc.lower().split(":")[0])
    return {d for d in out if d}


def domains_from_index(known: set[str], min_hits: int) -> list[str]:
    """Portal-shaped hostnames appearing in our own resource URLs."""
    conn = db_connect()
    counts: collections.Counter = collections.Counter()
    for (url,) in conn.execute("SELECT url FROM resources"):
        try:
            d = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
        except ValueError:
            continue  # publishers do store malformed URLs
        if d and d not in known:
            counts[d] += 1
    conn.close()
    hints = ("data", "opendata", "arcgis", "geoportal", "insight", "observatory")
    return [d for d, n in counts.most_common()
            if n >= min_hits and any(h in d for h in hints)]


def slugs_from_publishers() -> set[str]:
    """Guessable hostname slugs from the authority names we already hold."""
    conn = db_connect()
    names = [r[0] for r in conn.execute(
        "SELECT DISTINCT publisher FROM datasets WHERE publisher IS NOT NULL")]
    conn.close()

    slugs: set[str] = set()
    for name in names:
        low = name.lower()
        if not any(w in low for w in ("council", "borough", "county", "authority")):
            continue
        toks = [t for t in "".join(c if c.isalpha() else " " for c in low).split()
                if t not in _ORG_WORDS and len(t) > 2]
        if not toks:
            continue
        slugs.add(toks[-1])          # "Leeds City Council" -> leeds
        if len(toks) > 1:
            slugs.add("".join(toks))  # "Milton Keynes" -> miltonkeynes
    return slugs


def resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
        return True
    except OSError:
        return False


def probes_for(host: str) -> tuple:
    """Only try APIs the host could plausibly serve.

    ArcGIS Hub domains have wildcard DNS — every made-up subdomain resolves —
    so DNS can't filter them and the HTTP probe carries the whole load. They
    only ever speak DCAT, so probing CKAN there triples the request count for
    nothing.
    """
    if host.endswith((".arcgis.com",)):
        return tuple(p for p in API_PROBES if p[0] == "dcat")
    return API_PROBES


def probe(host: str) -> tuple[str, str, str, int] | None:
    """Return (host, kind, api_url, dataset_count) if it speaks a known API."""
    base = f"https://{host}"
    for kind, path, count in probes_for(host):
        try:
            r = requests.get(base + path, headers=UA, timeout=TIMEOUT)
            if not r.ok:
                continue
            n = count(r.json())
            if n:
                return (host, kind, base + path.split("?")[0], n)
        except Exception:  # noqa: BLE001
            continue
    return None


def yaml_entry(host: str, kind: str, api: str, n: int) -> str:
    slug = host.split(".")[0].replace("-", "_")
    dataset_url = ('"unused-for-dcat"' if kind == "dcat"
                   else f"https://{host}/dataset/{{name}}")
    api_line = api if kind == "dcat" else api.rsplit("/", 1)[0]
    return (f"  - id: {slug}\n"
            f"    name: TODO proper name ({n:,} datasets)\n"
            f"    type: {kind}\n"
            f"    api: {api_line}\n"
            f"    web: https://{host}\n"
            f"    dataset_url: {dataset_url}\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-index", action="store_true")
    ap.add_argument("--from-names", action="store_true")
    ap.add_argument("--min-hits", type=int, default=20,
                    help="min resource URLs before an indexed domain is a candidate")
    args = ap.parse_args()
    both = not (args.from_index or args.from_names)

    known = known_domains()
    candidates: set[str] = set()

    if both or args.from_index:
        found = domains_from_index(known, args.min_hits)
        print(f"signal 1 (our own index): {len(found)} portal-shaped domains")
        candidates |= set(found)

    if both or args.from_names:
        slugs = slugs_from_publishers()
        generated = {p.format(s=s) for s in slugs for p in HOST_PATTERNS}
        print(f"signal 2 (naming conventions): {len(slugs)} authority slugs "
              f"-> {len(generated):,} candidate hostnames")
        candidates |= generated

    candidates -= known
    print(f"\nresolving {len(candidates):,} candidates ...")
    with ThreadPoolExecutor(max_workers=50) as pool:
        live = [h for h, ok in zip(candidates, pool.map(resolves, candidates)) if ok]
    print(f"{len(live)} resolve; probing their APIs ...\n")

    with ThreadPoolExecutor(max_workers=24) as pool:
        hits = [r for r in pool.map(probe, live) if r]

    hits.sort(key=lambda r: -r[3])
    print(f"=== {len(hits)} harvestable portals found ===")
    for host, kind, _, n in hits:
        print(f"  {kind.upper():5} {n:>7,}  {host}")

    if hits:
        print("\n=== proposed sources.yaml entries (review before merging) ===")
        for hit in hits:
            print(yaml_entry(*hit))


if __name__ == "__main__":
    main()
