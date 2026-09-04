"""Build the semantic search index: embed every dataset's metadata and
store the vectors alongside a SQLite FTS5 keyword index.

Usage:
    python embed_index.py            # embeds all datasets missing from the index
    python embed_index.py --rebuild  # start from scratch

Outputs (both git-ignored, rebuildable from index.db):
    embeddings.npy   float32 matrix, one L2-normalised row per dataset
    emb_keys.json    dataset key for each row, same order
Also (re)builds the `fts` FTS5 table inside index.db.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from paths import DB_PATH, EMB_PATH, KEYS_PATH, connect as db_connect  # noqa: E402

# MiniLM-L6 + 256-token cap is ~4x faster than bge-small on CPU with only a
# modest retrieval-quality cost — right trade for the prototype. To upgrade
# later: change MODEL_NAME/QUERY_PREFIX and re-run with --rebuild.
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
QUERY_PREFIX = ""  # bge-style models want a query prefix; MiniLM doesn't
MAX_SEQ_TOKENS = 256
BATCH = 128
DESC_CHARS = 600
CHECKPOINT_EVERY = 5000  # save partial progress so a killed run resumes


def doc_text(row: sqlite3.Row) -> str:
    """The text we embed for one dataset: title, publisher, tags, description."""
    tags = ", ".join(json.loads(row["tags"] or "[]"))
    parts = [
        row["title"] or "",
        f"Publisher: {row['publisher']}" if row["publisher"] else "",
        f"Tags: {tags}" if tags else "",
        (row["description"] or "")[:DESC_CHARS],
    ]
    return "\n".join(p for p in parts if p)


def build_fts(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DROP TABLE IF EXISTS fts;
        CREATE VIRTUAL TABLE fts USING fts5(
            key UNINDEXED, title, description, publisher, tags,
            tokenize = 'porter unicode61'
        );
        """
    )
    conn.execute(
        """
        INSERT INTO fts (key, title, description, publisher, tags)
        SELECT key, coalesce(title,''), coalesce(description,''),
               coalesce(publisher,''), coalesce(tags,'')
        FROM datasets
        """
    )
    conn.commit()


VOCAB_MIN_DF = 3      # a word we would put in someone's mouth must be real


def build_vocab(conn: sqlite3.Connection) -> int:
    """The words readers actually see, for correcting the ones they type.

    Not fts5vocab: that table holds Porter stems, so offering "did you mean
    inflat" would be worse than saying nothing. Titles and tags are the
    human-facing vocabulary, counted per dataset so a word repeated inside
    one title doesn't look popular.

    Words appearing in fewer than VOCAB_MIN_DF datasets are dropped, because
    a suggestion pointing at somebody else's typo is still a typo.
    """
    df: collections.Counter[str] = collections.Counter()
    for title, tags in conn.execute(
            "SELECT coalesce(title,''), coalesce(tags,'') FROM datasets"):
        df.update(set(re.findall(r"[a-z]{3,}", (title + " " + tags).lower())))
    conn.executescript(
        "DROP TABLE IF EXISTS vocab;"
        "CREATE TABLE vocab (word TEXT PRIMARY KEY, df INTEGER NOT NULL);")
    conn.executemany("INSERT INTO vocab (word, df) VALUES (?, ?)",
                     [(w, n) for w, n in df.items() if n >= VOCAB_MIN_DF])
    conn.commit()
    return conn.execute("SELECT count(*) FROM vocab").fetchone()[0]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rebuild", action="store_true",
                    help="re-embed everything instead of just new datasets")
    args = ap.parse_args()

    conn = db_connect()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM datasets ORDER BY key").fetchall()
    print(f"{len(rows):,} datasets in index.db")

    print("rebuilding FTS5 keyword index ...")
    build_fts(conn)
    # Before the early return below: on a night with nothing new to embed
    # the spelling vocabulary must still track the catalogue it describes.
    print(f"spelling vocabulary: {build_vocab(conn):,} words")

    done_keys: list[str] = []
    done_vecs: np.ndarray | None = None
    if not args.rebuild and EMB_PATH.exists() and KEYS_PATH.exists():
        done_keys = json.loads(KEYS_PATH.read_text(encoding="utf-8"))
        done_vecs = np.load(EMB_PATH)
        if done_vecs.shape[0] != len(done_keys):  # corrupt/partial — start over
            done_keys, done_vecs = [], None

    # Drop vectors for datasets that have left the index. Nothing removed
    # them before, so the matrix only ever grew: 3,560 stale rows by
    # September 2026, and a home page announcing the semantic index was
    # 103% built. Pruned here so the file stays the size of the catalogue.
    live = {r["key"] for r in rows}
    keep = [i for i, k in enumerate(done_keys) if k in live]
    pruned = len(done_keys) - len(keep)
    if pruned:
        done_keys = [done_keys[i] for i in keep]
        done_vecs = done_vecs[keep]
        np.save(EMB_PATH, done_vecs)
        KEYS_PATH.write_text(json.dumps(done_keys), encoding="utf-8")
        print(f"pruned {pruned:,} embeddings for datasets no longer indexed")

    done_set = set(done_keys)
    todo = [r for r in rows if r["key"] not in done_set]
    print(f"{len(todo):,} datasets to embed "
          f"({len(done_keys):,} already embedded)")
    if not todo:
        print("nothing to do")
        return

    model = SentenceTransformer(MODEL_NAME)
    model.max_seq_length = MAX_SEQ_TOKENS

    keys = list(done_keys)
    matrix = done_vecs
    for i in range(0, len(todo), CHECKPOINT_EVERY):
        chunk = todo[i:i + CHECKPOINT_EVERY]
        vecs = model.encode(
            [doc_text(r) for r in chunk],
            batch_size=BATCH,
            show_progress_bar=False,
            normalize_embeddings=True,
        ).astype(np.float32)
        keys += [r["key"] for r in chunk]
        matrix = vecs if matrix is None else np.vstack([matrix, vecs])
        np.save(EMB_PATH, matrix)
        KEYS_PATH.write_text(json.dumps(keys), encoding="utf-8")
        print(f"checkpoint: {len(keys):,}/{len(rows):,} embedded", flush=True)

    print(f"saved {matrix.shape[0]:,} x {matrix.shape[1]} embeddings "
          f"({EMB_PATH.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
