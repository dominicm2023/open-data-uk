"""Relevance regression suite.

Ranking here is five interacting signals (semantic, keyword, rare-term,
publisher, geography, availability). Tuning one in isolation has repeatedly
broken another, so every change gets measured against the whole set.

Each case says what a *good* result list looks like:
    want   — at least one of the top N titles/publishers matches this regex
    avoid  — none of the top N should match this regex (optional)

Run on the VPS, against the live index, importing the engine directly:
    DATA_DIR=~/opendata-index/data .venv/bin/python scripts/relevance_test.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from search import SearchEngine  # noqa: E402

CASES = [
    # (query, top_n, want_regex, avoid_regex_or_None, why it matters)
    ("brighton recycling rates", 3, r"recycl|waste", r"brownfield|payments to suppliers|apprenticeship",
     "place + topic: must return RECYCLING data, not just any Brighton dataset"),
    ("recycling rates", 3, r"recycl", None,
     "topic alone must still work (it did before the place bug)"),
    ("bristol cycle paths", 3, r"cycl", None,
     "publisher boost: Bristol's datasets have generic titles"),
    ("car parks in calderdale", 2, r"park", None,
     "council-specific retrieval"),
    ("flood risk in brighton", 3, r"flood", None,
     "geo bbox: national EA data covering Brighton"),
    # FAILS on the live index as of 3 Sep 2026, and the cause is measured:
    # the boost picks the decisive term by document frequency, and the index
    # grew until 'waiting' (316) became RARER than 'allotment' (318). It now
    # boosts the wrong half of the query. No dataset anywhere holds both
    # words, so there is no right answer to rank first - but the distinctive
    # half should still win over the generic one. Fixing it means finding a
    # better notion of "decisive" than raw DF; a blanket demotion for records
    # missing the rare term was tried and does nothing, because the term it
    # selects is the wrong one to begin with.
    ("allotment waiting lists", 3, r"allotment", r"hospital|nhs",
     "rare-term boost must beat the common phrase 'waiting lists'"),
    ("winter gritting routes", 3, r"gritting", None,
     "plain topical query"),
    ("antidepressant prescriptions by GP practice", 3, r"prescri|antidepressant", None,
     "health known-item"),
    ("hospital waiting times northern ireland", 3, r"waiting", None,
     "nation-level geography"),
    ("air quality in leeds", 3, r"leeds", None,
     "local authority should beat other councils for its own name"),
    ("electric vehicle charging points", 3, r"charg", None,
     "original smoke test"),
    ("heritage at risk register", 3, r"heritage at risk", None,
     "Historic England known-item"),
    # A real visitor's query, 31 Aug 2026. The dataset of exactly this name
    # existed, with a verified file, and sat outside the top ten - beaten by
    # three copies of a JNCC habitats report, because nothing in the ranking
    # distinguished a title from a neighbour in embedding space. They
    # reformulated twice and left.
    ("North Yorkshire Article 4", 1, r"north yorkshire article 4", None,
     "typing a dataset's exact name must return that dataset first"),
]

# What we *say* about a result list, which is a separate claim from what is
# in it. A visitor searched "inequality" on 2 Sep 2026 and was told nothing
# matched well, above ONS's Household Disposable Income and Inequality.
CONFIDENCE_CASES = [
    # (query, expected confidence, why it matters)
    ("inequality", "strong",
     "one abstract word embeds diffusely; the titles carry it plainly"),
    ("Uprn", "strong", "an acronym the embedding cannot know, matched exactly"),
    ("spend over 500", "strong", "the reader typed the datasets' own name"),
    ("lyme", "weak",
     "matches Newcastle-under-Lyme and Lyme Regis - a place fragment, not "
     "the subject anyone means by it"),
    ("data", "weak",
     "in half the index: a title match on it is evidence of nothing"),
    ("hello", "none", "not a subject; saying so is the whole point"),
    ("east sussex SEND rates", "weak",
     "the place matched and the topic did not - demotion must still bite"),
]


def run_confidence(engine) -> tuple[int, int]:
    passed = failed = 0
    for query, want, why in CONFIDENCE_CASES:
        got = engine.search(query, 5)["confidence"]
        ok = got == want
        passed += ok
        failed += not ok
        print("%s  confidence(%r) == %s" % ("PASS" if ok else "FAIL", query, want))
        if not ok:
            print("       got %r; why it matters: %s" % (got, why))
    return passed, failed



def run() -> int:
    engine = SearchEngine()
    passed = failed = 0
    for query, top_n, want, avoid, why in CASES:
        payload = engine.search(query, top_n)
        rows = payload["results"]
        blob = [f"{r['title']} {r['publisher'] or ''}" for r in rows]
        hit = any(re.search(want, t, re.I) for t in blob)
        bad = [t for t in blob if avoid and re.search(avoid, t, re.I)]
        ok = hit and not bad
        passed += ok
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {query}")
        if not ok:
            print(f"       want /{want}/ in top {top_n}"
                  + (f", avoid /{avoid}/" if avoid else ""))
            print(f"       why: {why}")
            for i, r in enumerate(rows, 1):
                mark = "  <-- unwanted" if avoid and re.search(avoid, blob[i - 1], re.I) else ""
                print(f"         {i}. {r['title'][:58]}{mark}")
    cp, cf = run_confidence(engine)
    passed, failed = passed + cp, failed + cf
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(run())
