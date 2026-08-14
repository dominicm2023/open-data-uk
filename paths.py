"""Data-file locations, overridable with the DATA_DIR environment variable
(used by the Docker image, which mounts the built index as a volume)."""

import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT))

DB_PATH = DATA_DIR / "index.db"
EMB_PATH = DATA_DIR / "embeddings.npy"
KEYS_PATH = DATA_DIR / "emb_keys.json"


def connect() -> sqlite3.Connection:
    """Open index.db configured for concurrent use (harvester, checker and
    the web server routinely run at the same time)."""
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=15000")
    return conn
