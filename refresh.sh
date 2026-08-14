#!/usr/bin/env bash
# Scheduled index refresh. Run from cron — see DEPLOY.md for the crontab line.
#
# Everything here is incremental and safe to re-run: the harvester upserts,
# embedding only touches datasets it hasn't seen, and the checker works
# through a rolling slice of URLs so the whole index gets re-verified about
# once a month without ever hammering publishers.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PY:-.venv/bin/python}"
CHECK_LIMIT="${CHECK_LIMIT:-2500}"   # URLs per night (~51k index / 30 days)
CHECK_WORKERS="${CHECK_WORKERS:-8}"  # deliberately polite on a shared box

echo "=====REFRESH-RUN===== $(date -Is)"
"$PY" harvester.py
"$PY" embed_index.py
"$PY" dedupe.py
"$PY" checker.py --limit "$CHECK_LIMIT" --workers "$CHECK_WORKERS"
echo "=====REFRESH-DONE===== $(date -Is)"

# The running server picks up new embeddings and DB rows on its next query —
# no restart needed for data changes, only for code changes.
