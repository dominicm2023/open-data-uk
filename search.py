"""Hybrid search over the index: semantic (embeddings) + keyword (FTS5 BM25),
fused with reciprocal rank fusion, plus:

- title-weighted BM25 (a match in the title outranks one buried in text)
- rare-term bonus: for multi-concept queries ("allotment waiting lists"),
  results containing the rarest — most informative — query term get a boost
- duplicate collapapse and retired-record filtering (see dedupe.py)
- a confidence signal so the UI can say "no strong matches" instead of
  presenting nearest-neighbour noise as an answer

CLI:
    python search.py "ev charging points in manchester"
    python search.py "hospital waiting times" -k 5 --json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
from pathlib import Path

import numpy as np

from embed_index import MODEL_NAME, QUERY_PREFIX
from geo import (build_place_vocab, detect_place, mentions_place,
                 place_coverage, place_point)

from paths import DB_PATH, EMB_PATH, KEYS_PATH, connect as db_connect  # noqa: E402

RRF_K = 60          # standard reciprocal-rank-fusion constant
CANDIDATES = 100    # depth taken from each retriever before fusion

# Boosts are MULTIPLICATIVE, deliberately.
#
# They used to be additive constants (0.02-0.03). But RRF scores rank 1 at
# 1/(60+1)=0.0164 and rank 50 at 0.0090 — the entire relevance spread is
# ~0.007, so a 0.025 bonus was worth more than the difference between the
# best and the 50th-best match. Any single signal silently decided the
# ordering: "brighton recycling rates" returned Brighton *brownfield land*
# because the publisher boost outweighed the topic entirely.
# Multiplying preserves the relevance ordering and lets signals modulate it.
RARE_TERM_BOOST = 1.30
PUBLISHER_BOOST = 1.35
GEO_BOOST = 1.45
RARE_TERM_MAX_DF = 5000   # if even the rarest term is commoner, skip the bonus
PUBLISHER_MAX_DF = 1500   # ignore terms matching many publishers ("council", "city")
# Verified availability nudges; "blocked" is absent on purpose (we know
# nothing about it, so it must not move the result either way).
AVAILABILITY_MULT = {"data": 1.15, "api": 1.05, "webpage": 0.97, "dead": 0.85}
NO_FILES_MULT = 0.95
# "brighton recycling rates" shouldn't surface Brighton's supplier payments:
# matching the place but nothing of the topic is weak evidence. Kept gentle
# (not a filter) because the semantic arm legitimately finds datasets that
# never use the query's words — "kerbside collection tonnages" is recycling.
PLACE_ONLY_MULT = 0.80
# A dataset whose own bbox lies wholly on another continent, reached via the
# research catalogues. Demoted, never hidden — see _dup_and_retired.
FOREIGN_MULT = 0.50
# bm25 column weights: key(unindexed), title, description, publisher, tags
BM25_WEIGHTS = "0.0, 5.0, 1.0, 2.0, 3.0"
# cosine similarity of the best semantic hit, used for the confidence signal
SIM_STRONG = 0.55
SIM_WEAK = 0.40


class SearchEngine:
    def __init__(self) -> None:
        self._model = None
        self._matrix: np.ndarray | None = None
        self._keys: list[str] = []
        self._emb_mtime = 0.0
        self._place_vocab: set[str] | None = None
        self._dup_cache: tuple[dict, set] | None = None
        self._dup_mtime = 0.0

    @property
    def model(self):
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer
            # One thread per request. Encoding a single short query takes
            # ~12 ms; letting torch grab all 8 cores for it just makes
            # concurrent requests fight each other, which is worse than
            # useless when the real concurrency comes from serving many
            # users at once rather than one query faster.
            torch.set_num_threads(1)
            self._model = SentenceTransformer(MODEL_NAME)
        return self._model

    def _vectors(self) -> tuple[np.ndarray | None, list[str]]:
        """Load embeddings, hot-reloading if a newer checkpoint exists."""
        if not EMB_PATH.exists():
            return None, []
        mtime = EMB_PATH.stat().st_mtime
        if self._matrix is None or mtime > self._emb_mtime:
            try:
                # mmap: four workers each held a private ~158MB copy, and
                # the nightly hot-reload doubled it transiently against a
                # 3G MemoryMax — an OOM trajectory as the index grows.
                matrix = np.load(EMB_PATH, mmap_mode="r")
                keys = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
            except Exception:
                # embed_index.py may be mid-checkpoint; keep serving old vectors
                return self._matrix, self._keys
            if matrix.shape[0] == len(keys):
                self._matrix, self._keys, self._emb_mtime = matrix, keys, mtime
        return self._matrix, self._keys

    def _conn(self) -> sqlite3.Connection:
        conn = db_connect()
        conn.row_factory = sqlite3.Row
        return conn

    def vector_ranks(self, query: str) -> tuple[list[str], float]:
        """Ranked keys plus the best cosine similarity (confidence signal)."""
        matrix, keys = self._vectors()
        if matrix is None:
            return [], 0.0
        qvec = self.model.encode([QUERY_PREFIX + query], normalize_embeddings=True)[0]
        sims = matrix @ qvec
        top = np.argsort(-sims)[:CANDIDATES]
        return [keys[i] for i in top], float(sims[top[0]]) if len(top) else 0.0

    def keyword_ranks(self, query: str, conn: sqlite3.Connection,
                      place: str | None = None) -> list[str]:
        terms = self._terms(query)
        # A detected place's own words otherwise crowd out the topic: bm25
        # over "air OR quality OR newcastle OR upon OR tyne" ranks anything
        # the city publishes above actual air-quality data, because one
        # publisher hit supplies three of the five terms. The geo and
        # publisher arms carry the place; this arm carries the subject. A
        # query that is only a place keeps its terms.
        place_toks = set((place or "").split())
        topic = [t for t in terms if t not in place_toks]
        if topic:
            terms = topic
        if not terms:
            return []
        match = " OR ".join(terms)
        rows = conn.execute(
            f"SELECT key FROM fts WHERE fts MATCH ? "
            f"ORDER BY bm25(fts, {BM25_WEIGHTS}) LIMIT ?",
            (match, CANDIDATES),
        ).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def _terms(query: str) -> list[str]:
        # Sanitise into bare terms so user text can't break FTS5 syntax
        return re.findall(r"[A-Za-z0-9]+", query.lower())

    def _rare_term_keys(self, query: str, conn: sqlite3.Connection) -> set[str]:
        """Keys of datasets containing the rarest (most informative) query term.

        For "allotment waiting lists", 'allotment' (132 datasets) decides
        relevance far more than 'waiting' or 'lists' — without this, common
        phrases drown the term the user actually cares about.
        """
        terms = [t for t in self._terms(query) if len(t) > 2]
        if len(terms) < 2:
            return set()  # single-concept query; nothing to arbitrate
        dfs = []
        for t in terms:
            df = conn.execute(
                "SELECT COUNT(*) FROM fts WHERE fts MATCH ?", (t,)
            ).fetchone()[0]
            if df:
                dfs.append((df, t))
        if not dfs:
            return set()
        dfs.sort()
        df, rare = dfs[0]
        if df > RARE_TERM_MAX_DF:  # even the rarest term is common — no decisive term
            return set()
        rows = conn.execute(
            "SELECT key FROM fts WHERE fts MATCH ? LIMIT ?", (rare, RARE_TERM_MAX_DF)
        ).fetchall()
        return {r[0] for r in rows}

    def geo_ranks(self, query: str, conn: sqlite3.Connection,
                  point: tuple[float, float], place: str) -> list[str]:
        """Datasets whose published bounding box actually contains the place.

        This is the arm that finds national datasets covering somewhere —
        the Environment Agency's England-wide flood map genuinely covers
        Brighton even though it never says the word. Ranked by keyword
        relevance on the *non-place* terms, so "flood risk in brighton"
        matches on 'flood risk'.
        """
        terms = [t for t in self._terms(query) if t not in place.split() and len(t) > 2]
        if not terms:
            return []
        # AND, not OR. This arm *injects* results the other retrievers never
        # saw, so it has to be precise: OR-ing "car parks" matched every park
        # boundary that happened to cover Brighton.
        match = " ".join(terms)
        lon, lat = point
        try:
            rows = conn.execute(
                f"SELECT f.key FROM fts f "
                f"JOIN dataset_geo g ON g.dataset_key = f.key "
                f"WHERE fts MATCH ? "
                f"  AND g.bbox_west <= ? AND g.bbox_east >= ? "
                f"  AND g.bbox_south <= ? AND g.bbox_north >= ? "
                f"ORDER BY bm25(fts, {BM25_WEIGHTS}) LIMIT ?",
                (match, lon, lon, lat, lat, CANDIDATES),
            ).fetchall()
        except sqlite3.OperationalError:   # dataset_geo not built yet
            return []
        return [r[0] for r in rows]

    def _topic_match_keys(self, query: str, conn: sqlite3.Connection,
                          place: str | None) -> set[str] | None:
        """Keys matching the query's non-place terms.

        Returns None when the query is *only* a place (nothing to gate on).
        """
        place_toks = set((place or "").split())
        topic = [t for t in self._terms(query) if t not in place_toks and len(t) > 2]
        if not topic:
            return None
        rows = conn.execute(
            "SELECT key FROM fts WHERE fts MATCH ? LIMIT ?",
            (" OR ".join(topic), 20000),
        ).fetchall()
        return {r[0] for r in rows}

    def _publisher_match_keys(self, query: str, conn: sqlite3.Connection,
                              topic_keys: set[str] | None) -> set[str]:
        """Keys whose publisher contains a discriminating query term AND which
        are topically relevant.

        The topical gate is the important half. Matching on publisher alone
        boosted *every* dataset a place publishes, so "brighton recycling
        rates" surfaced Brighton's brownfield register and supplier payments
        — the borough is right, the subject is irrelevant. Brighton publishes
        no recycling data at all, and the honest answer is DEFRA's
        borough-level recycling table, which the boost was burying.
        """
        keys: set[str] = set()
        for t in self._terms(query):
            if len(t) <= 3:
                continue
            rows = conn.execute(
                "SELECT key FROM fts WHERE fts MATCH ? LIMIT ?",
                (f"publisher:{t}", PUBLISHER_MAX_DF + 1),
            ).fetchall()
            if 0 < len(rows) <= PUBLISHER_MAX_DF:
                keys |= {r[0] for r in rows}
        return keys & topic_keys if topic_keys is not None else keys

    @staticmethod
    def _availability(conn: sqlite3.Connection,
                      keys: list[str]) -> dict[str, tuple[str | None, int]]:
        """key -> (availability verdict or None, resource_count)."""
        if not keys:
            return {}
        try:
            marks = ",".join("?" * len(keys))
            rows = conn.execute(
                f"SELECT key, availability, resource_count FROM datasets "
                f"WHERE key IN ({marks})", keys).fetchall()
        except sqlite3.OperationalError:  # checker.py has not run yet
            return {}
        return {r[0]: (r[1], r[2] or 0) for r in rows}

    @staticmethod
    def _columns_for_keys(conn: sqlite3.Connection,
                          keys: list[str]) -> dict[str, list[str]]:
        """CSV column names per dataset, for the whole result page at once.

        One query for the page rather than one per result — at k=50 that was
        50 round trips to render a single response.
        """
        if not keys:
            return {}
        marks = ",".join("?" * len(keys))
        try:
            rows = conn.execute(
                f"SELECT r.dataset_key, c.columns FROM resources r "
                f"JOIN resource_checks c ON c.url = r.url "
                f"WHERE r.dataset_key IN ({marks}) AND c.columns IS NOT NULL",
                keys).fetchall()
        except sqlite3.OperationalError:
            return {}
        out: dict[str, list[str]] = {}
        for key, cols in rows:
            if key not in out:          # first resource with columns wins
                out[key] = json.loads(cols)
        return out

    def _dup_and_retired(self, conn: sqlite3.Connection) -> tuple[dict, set, set]:
        """Duplicate and retired keys, cached in memory.

        These tables only change when dedupe.py runs, but re-reading all
        ~19,000 rows on *every* search was the single biggest cost in a
        query — far more than the embedding maths. Cached against the
        database's mtime so a nightly refresh is still picked up without a
        restart.
        """
        try:
            mtime = DB_PATH.stat().st_mtime
        except OSError:
            mtime = 0.0
        if self._dup_cache is None or mtime > self._dup_mtime:
            try:
                dups = dict(conn.execute(
                    "SELECT key, canonical_key FROM duplicates").fetchall())
                retired = {r[0] for r in conn.execute("SELECT key FROM retired")}
            except sqlite3.OperationalError:  # dedupe.py not run yet
                return {}, set(), set()
            # Records whose own bbox lies wholly on another continent:
            # UK research institutions publish Panama, Uganda and Vietnam
            # studies through the research catalogues on data.gov.uk, and
            # they were outranking UK-scoped answers in a UK index. The box
            # is deliberately generous — UK waters, the North Sea, the
            # Arctic surveys all stay inside it — and the records are only
            # demoted, never hidden: a search that genuinely wants the
            # Vietnam land-cover study has nothing UK competing with it.
            try:
                foreign = {r[0] for r in conn.execute(
                    "SELECT dataset_key FROM dataset_geo "
                    "WHERE bbox_west IS NOT NULL "
                    "  AND (bbox_east < -30.0 OR bbox_west > 15.0 "
                    "       OR bbox_north < 40.0)")}
            except sqlite3.OperationalError:
                foreign = set()
            self._dup_cache = (dups, retired, foreign)
            self._dup_mtime = mtime
        return self._dup_cache

    @staticmethod
    def _filter_ranked(conn: sqlite3.Connection, ranked: list[str],
                       availability: dict, filters: dict) -> list[str]:
        """Drop candidates that don't match the requested constraints.

        Applied after ranking and before paging, so `available` stays an
        honest count of what a client can page through — filtering after the
        slice would hand back short pages and a total that lied about them.

        Every filter takes a comma-separated list and means OR within itself,
        AND between fields: format=CSV,XLSX & availability=data is "a
        spreadsheet or a CSV, and we checked the link and it really is a file".
        """
        if not ranked or not filters:
            return ranked
        marks = ",".join("?" * len(ranked))
        rows = {r["key"]: r for r in conn.execute(
            f"SELECT key, source_id, license_norm, formats_norm FROM datasets "
            f"WHERE key IN ({marks})", ranked)}

        want_source = filters.get("source")
        want_licence = filters.get("license")
        want_format = filters.get("format")
        want_avail = filters.get("availability")

        kept = []
        for key in ranked:
            row = rows.get(key)
            if row is None:
                continue
            if want_source and (row["source_id"] or "").lower() not in want_source:
                continue
            if want_licence:
                lic = (row["license_norm"] or "").lower()
                # "none" is a real answer to "what licence is this under?",
                # and the one a third of the catalogue gives.
                # "ogl" means the whole family: stored values are always
                # versioned (ogl-uk-3.0), and asking for the bare name used
                # to return zero results silently.
                if not (lic in want_licence
                        or (not lic and "none" in want_licence)
                        or ("ogl" in want_licence and lic.startswith("ogl-uk"))):
                    continue
            if want_format:
                have = {f.lower() for f in json.loads(row["formats_norm"] or "[]")}
                if not (have & want_format):
                    continue
            if want_avail:
                verdict, _ = availability.get(key, (None, 0))
                if (verdict or "unchecked") not in want_avail:
                    continue
            kept.append(key)
        return kept

    def search(self, query: str, k: int = 10, offset: int = 0,
               filters: dict | None = None) -> dict:
        conn = self._conn()
        try:
            if self._place_vocab is None:
                self._place_vocab = build_place_vocab(conn)
            place = detect_place(query, self._place_vocab)
            point = place_point(place)

            vec_keys, top_sim = self.vector_ranks(query)
            # Only strip the place from the keyword arm when the geo arm is
            # there to carry it: for a place without coordinates ("brighton"
            # is not an LAD name), the keyword hit on the publisher is the
            # only locality signal there is.
            kw_keys = self.keyword_ranks(query, conn, place if point else None)
            geo_keys = (self.geo_ranks(query, conn, point, place)
                        if point and place else [])
            rare_keys = self._rare_term_keys(query, conn)
            topic_keys = self._topic_match_keys(query, conn, place)
            pub_keys = self._publisher_match_keys(query, conn, topic_keys)
            dups, retired, foreign = self._dup_and_retired(conn)

            fused: dict[str, float] = {}
            for ranked in (vec_keys, kw_keys, geo_keys):
                for rank, key in enumerate(ranked):
                    fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)
            # A dataset whose own bbox covers the place is a real geographic
            # match, so lift it — but nothing is ever pushed *down* for
            # lacking a bbox: only ~35% of datasets publish one at all.
            geo_set = set(geo_keys)
            availability = self._availability(conn, list(fused))
            for key in list(fused):
                mult = 1.0
                if key in rare_keys:
                    mult *= RARE_TERM_BOOST
                if key in pub_keys:
                    mult *= PUBLISHER_BOOST
                # A geo match earns nothing when the links are dead (1.45 ×
                # 0.85 still beat clean results — "air quality cardiff" led
                # with a dead record whose box spanned the UK), and nothing
                # when the record missed the topic: boosted-then-demoted
                # came to 1.45 × 0.80 = a net *lift* for matching the place
                # alone, which put Newcastle's conservation areas above
                # actual air quality data.
                verdict_now, _ = availability.get(key, (None, 0))
                place_only = (place and topic_keys is not None
                              and key not in topic_keys)
                if key in geo_set and verdict_now != "dead" and not place_only:
                    mult *= GEO_BOOST
                # matched the place but nothing of what was actually asked
                if place_only:
                    mult *= PLACE_ONLY_MULT
                verdict, n_res = availability.get(key, (None, 0))
                if verdict:
                    mult *= AVAILABILITY_MULT.get(verdict, 1.0)
                elif n_res == 0:
                    mult *= NO_FILES_MULT
                if key in foreign:
                    mult *= FOREIGN_MULT
                fused[key] *= mult

            # collapse duplicates onto their canonical copy, drop retired
            collapsed: dict[str, float] = {}
            for key, score in fused.items():
                canon = dups.get(key, key)
                if canon in retired:
                    continue
                collapsed[canon] = max(collapsed.get(canon, 0.0), score)

            ranked = sorted(collapsed, key=collapsed.get, reverse=True)
            ranked = self._filter_ranked(conn, ranked, availability, filters or {})
            total = len(ranked)
            top = ranked[offset:offset + k]
            columns_by_key = self._columns_for_keys(conn, top)
            results = []
            for key in top:
                row = conn.execute(
                    "SELECT * FROM datasets WHERE key = ?", (key,)
                ).fetchone()
                if not row:
                    continue
                verdict, _ = availability.get(key, (None, 0))
                results.append({
                    "key": key,
                    "score": round(collapsed[key], 4),
                    "title": row["title"],
                    "publisher": row["publisher"],
                    "source": row["source_id"],
                    "license": row["license_norm"],
                    "formats": json.loads(row["formats_norm"]),
                    "modified": (row["modified"] or "")[:10],
                    "url": row["landing_url"],
                    "description": (row["description"] or "")[:280],
                    "availability": verdict,
                    "columns": columns_by_key.get(key),
                    "covers_place": key in geo_set or None,
                })

            # Keyword OR-queries match almost anything, so confidence rests on
            # semantic similarity alone
            if top_sim >= SIM_STRONG:
                confidence = "strong"
            elif top_sim >= SIM_WEAK:
                confidence = "weak"
            else:
                confidence = "none"

            # geography honesty: did the user name a place, do we hold data
            # for it, and do the results actually come from there?
            geo = None
            if place:
                geo = {
                    "place": place,
                    "point": list(point) if point else None,
                    "coverage": place_coverage(place, conn),
                    # Results whose published boundary contains the place —
                    # usually national datasets that genuinely cover it.
                    "bbox_matches": sum(1 for r in results if r.get("covers_place")),
                    # Deliberately NOT counting bbox matches: a UK-wide LIDAR
                    # survey covering Brighton doesn't mean we hold Brighton
                    # data, and letting it suppress the warning would make us
                    # look more useful than we are.
                    "in_results": any(mentions_place(r, place) for r in results),
                }

            return {
                "query": query,
                "confidence": confidence,
                "top_similarity": round(top_sim, 3),
                "offset": offset,
                # How many ranked candidates exist for this query. Not the
                # number of matching datasets in the index — retrieval is
                # capped at CANDIDATES per arm — so it is an honest "how much
                # more can you page through", not a corpus-wide total.
                "available": total,
                # Echoed back as sorted lists: sets don't survive JSON, and a
                # client that mistypes a filter should be able to see what we
                # actually applied rather than guess from an empty result.
                "filters": ({name: sorted(vals) for name, vals in filters.items()}
                            if filters else None),
                "geo": geo,
                "results": results,
            }
        finally:
            conn.close()

    def stats(self) -> dict:
        conn = self._conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
            by_source = dict(conn.execute(
                "SELECT source_id, COUNT(*) FROM datasets GROUP BY source_id"
            ).fetchall())
            publishers = conn.execute(
                "SELECT COUNT(DISTINCT publisher) FROM datasets"
            ).fetchone()[0]
            try:
                dup_count = conn.execute("SELECT COUNT(*) FROM duplicates").fetchone()[0]
            except sqlite3.OperationalError:
                dup_count = 0
        finally:
            conn.close()
        matrix, _ = self._vectors()
        return {
            "datasets": total,
            "sources": by_source,
            "publishers": publishers,
            "duplicates_collapsed": dup_count,
            "embedded": 0 if matrix is None else int(matrix.shape[0]),
        }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query")
    ap.add_argument("-k", type=int, default=10, help="number of results")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    payload = SearchEngine().search(args.query, args.k)
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    if payload["confidence"] != "strong":
        print(f"[{payload['confidence']} match — best similarity "
              f"{payload['top_similarity']}; results may be tangential]\n")
    for i, r in enumerate(payload["results"], 1):
        fmts = "/".join(r["formats"][:4]) or "no files"
        lic = r["license"] or "no licence"
        print(f"{i:2}. {r['title']}")
        print(f"    {r['publisher'] or '(unknown publisher)'} · {r['source']}"
              f" · {lic} · {fmts} · updated {r['modified'] or '?'}")
        print(f"    {r['url']}")
        if r["description"]:
            print(f"    {r['description'][:160]}")
        print()


if __name__ == "__main__":
    main()
