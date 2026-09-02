"""Anonymous search-query logging, for relevance analysis.

Ranking here is tuned against a 12-case test suite written by its author,
which is thin evidence. What people actually type — especially the queries
that come back weak, empty, or wrong — is far better evidence, and it is the
only way to find the failures nobody thought to test for.

PRIVACY, deliberately:
  * No IP address, no user agent, no session or cookie identifier, nothing
    that links one query to another or to a person. A query plus an IP is
    personal data; a query on its own, in a pile of other queries, is not.
  * Stored separately from the index (queries.db) so it is never bundled
    into a published snapshot, and it is git-ignored.
  * Logging can never break a search: every failure here is swallowed.

The point is to answer questions like "which searches disappoint people?",
not "what did this person search for".

The clicks table is the other half of the same question. A result's title
links straight out to the publisher, so a search that answered somebody and a
search that wasted their time leave identical rows in `queries` — which is
why we counted 68 searches and could not say whether one of them worked.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from paths import DATA_DIR

LOG_PATH = Path(DATA_DIR) / "queries.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    ts             TEXT NOT NULL,
    query          TEXT NOT NULL,
    k              INTEGER,
    confidence     TEXT,      -- strong | weak | none
    top_similarity REAL,
    n_results      INTEGER,
    place          TEXT,      -- detected UK place, if any
    bbox_matches   INTEGER,
    top_key        TEXT       -- winning dataset, to spot bad #1s
);
CREATE INDEX IF NOT EXISTS idx_queries_ts   ON queries (ts);
CREATE INDEX IF NOT EXISTS idx_queries_conf ON queries (confidence);

CREATE TABLE IF NOT EXISTS clicks (
    ts    TEXT NOT NULL,
    query TEXT NOT NULL,   -- the search this result came from
    key   TEXT NOT NULL,   -- the dataset opened
    rank  INTEGER,         -- where it sat in the results, 1-based
    kind  TEXT             -- outbound (to the publisher) | details (our page)
);
CREATE INDEX IF NOT EXISTS idx_clicks_ts ON clicks (ts);
"""

# What a click beacon is allowed to say it was.
CLICK_KINDS = ("outbound", "details")

_ready = False


def _connect() -> sqlite3.Connection:
    global _ready
    conn = sqlite3.connect(LOG_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    if not _ready:
        conn.executescript(SCHEMA)
        _ready = True
    return conn


def log_query(query: str, k: int, payload: dict) -> None:
    """Record one search. Never raises — a logging fault must not 500 a user."""
    try:
        geo = payload.get("geo") or {}
        results = payload.get("results") or []
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO queries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    (query or "")[:500],
                    k,
                    payload.get("confidence"),
                    payload.get("top_similarity"),
                    len(results),
                    geo.get("place"),
                    geo.get("bbox_matches"),
                    results[0]["key"] if results else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — logging is best-effort by design
        pass


def log_click(query: str, key: str, rank: int | None, kind: str) -> None:
    """Record that a search result was opened. Never raises, as above.

    Stores no more than log_query already does — the search text, and now
    which of its results was worth opening. Still nothing that ties two rows
    to one person.
    """
    try:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO clicks VALUES (?, ?, ?, ?, ?)",
                (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    (query or "")[:500],
                    (key or "")[:300],
                    rank,
                    kind,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — logging is best-effort by design
        pass
