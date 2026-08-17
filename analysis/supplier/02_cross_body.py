# 02_cross_body.py — Q2: how many supplier strings recur across publishers,
# by exact match and after a CONSERVATIVE normalisation. The gap between the
# two is the measurable cost of publishing names without identifiers.
#
# Normalisation (deliberately minimal, no fuzzy matching):
#   upper-case; punctuation -> space; drop tokens LTD/LIMITED/PLC/AND/&;
#   drop leading THE; collapse whitespace.
# "AND"/& is dropped because & was already punctuation-stripped, so keeping
# the word AND would split "MARKS AND SPENCER" from "MARKS & SPENCER".
import sqlite3, os, re, json, csv
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
con = sqlite3.connect(os.path.join(HERE, "agg.db"))

DROP = {"LTD", "LIMITED", "PLC", "AND"}
_punct = re.compile(r"[^A-Z0-9 ]+")

def norm(s: str) -> str:
    s = _punct.sub(" ", s.upper())
    toks = [t for t in s.split() if t not in DROP]
    if toks and toks[0] == "THE":
        toks = toks[1:]
    return " ".join(toks)

def dist(counts):
    return {f"{k}+": sum(1 for c in counts if c >= k) for k in (2, 3, 5, 10, 20)}

def main():
    # exact: s table already has per-string publisher counts
    exact_counts = [r[0] for r in con.execute("SELECT publishers FROM s")]
    n_exact = len(exact_counts)

    # normalised: rebuild publisher sets per normalised string from sp
    npubs = defaultdict(set)
    ngbp = defaultdict(float)
    nvariants = defaultdict(set)
    for raw, pub, gbp in con.execute("SELECT supplier_raw, publisher, gbp FROM sp"):
        nn = norm(raw)
        if not nn:
            continue
        npubs[nn].add(pub)
        ngbp[nn] += gbp
        nvariants[nn].add(raw)
    norm_counts = [len(v) for v in npubs.values()]

    out = {
        "clean_set": "is_dup=0 AND supplier_raw<>''",
        "distinct_supplier_strings_exact": n_exact,
        "distinct_supplier_strings_normalised": len(npubs),
        "exact_match_publishers": dist(exact_counts),
        "normalised_publishers": dist(norm_counts),
        "normalisation": "upper; punctuation->space; drop LTD/LIMITED/PLC/AND tokens; drop leading THE; collapse spaces",
    }
    print(json.dumps(out, indent=2))

    # biggest gainers: normalised names whose publisher count grew most vs their best exact string
    best_exact = defaultdict(int)
    for raw, pubs in con.execute("SELECT supplier_raw, publishers FROM s"):
        nn = norm(raw)
        if nn:
            best_exact[nn] = max(best_exact[nn], pubs)
    gain = sorted(
        ((nn, len(p), best_exact[nn], len(nvariants[nn]), ngbp[nn]) for nn, p in npubs.items()),
        key=lambda x: (x[1] - x[2], x[1]), reverse=True)
    with open(os.path.join(HERE, "cross_body_gainers.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["normalised_name", "publishers_normalised", "publishers_best_exact_string", "exact_strings_merged", "gbp"])
        for g in gain[:200]:
            w.writerow([g[0], g[1], g[2], g[3], round(g[4], 2)])
    print("\ntop 20 gainers (normalised pubs vs best single exact string):")
    for g in gain[:20]:
        print(f"  {g[1]:>3} vs {g[2]:>3} ({g[3]} strings, {g[4]:>16,.0f}) {g[0][:70]}")
    with open(os.path.join(HERE, "cross_body.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

if __name__ == "__main__":
    main()
