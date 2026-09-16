#!/usr/bin/env bash
# Health check for the UK Open Data Index, run from cron every 5 minutes.
#
# Checks the things that actually go wrong for this service, rather than just
# "is the process alive":
#   1. Does it answer a real search? (up-but-broken is the common failure)
#   2. Is the service unit running?
#   3. Is there disk headroom? (the index and logs grow)
#   4. Did the nightly refresh actually run? (silent staleness is the worst
#      failure here — everything looks fine while the data rots)
#
# On a failed HTTP check it restarts the service ONCE and re-tests, because
# the overwhelmingly likely cause is a wedged worker. Everything else is
# reported, not acted on: this box also runs a production site and a
# monitoring script should never be the thing that breaks it.
#
# Install:
#   */5 * * * * /home/ubuntu/opendata-index/scripts/healthcheck.sh >> /home/ubuntu/opendata-index/data/health.log 2>&1
set -uo pipefail

BASE="${HEALTH_BASE:-http://127.0.0.1:8010}"
DATA_DIR="${DATA_DIR:-/home/ubuntu/opendata-index/data}"
SERVICE="opendata-index"
REFRESH_LOG="$DATA_DIR/cron_refresh.log"
DISK_MIN_GB=5
REFRESH_MAX_HOURS=36        # nightly job, so >36h means it missed one

ts() { date -Is; }
fail=0
say() { echo "$(ts) $*"; }

# curl prints 000 itself when nothing answers; the fallback only covers curl
# not running at all (an earlier version appended a second 000 to the first).
probe() { curl -s -o "${1:-/dev/null}" -w "%{http_code}" --max-time 25 \
          "$BASE/api/search?q=health+check&k=1" 2>/dev/null || true; }

# 1. Does it actually answer a search?
code=$(probe /tmp/hc_body); code="${code:-000}"
if [ "$code" != "200" ]; then
  # A deploy restarts the service; its workers take ~15s to load the model.
  # If the unit came up within the last two minutes this is that, not a
  # wedged worker: wait for it rather than restart it a second time, which
  # only doubles the blip (15 Sep: two amber checks, both deploys).
  up_since=$(systemctl show -p ActiveEnterTimestampMonotonic --value "$SERVICE" 2>/dev/null || echo 0)
  now_mono=$(awk '{printf "%d", $1 * 1000000}' /proc/uptime)
  age=$(( (now_mono - ${up_since:-0}) / 1000000 ))
  if [ "$age" -ge 0 ] && [ "$age" -lt 120 ]; then
    for _ in 1 2 3 4 5 6; do
      sleep 10
      code=$(probe); code="${code:-000}"
      [ "$code" = "200" ] && break
    done
    [ "$code" = "200" ] && say "ok  http=200 after a restart ${age}s earlier (waited, did not restart)"
  fi
fi
if [ "$code" != "200" ]; then
  say "FAIL http search returned $code — restarting $SERVICE once"
  systemctl --user restart "$SERVICE" 2>/dev/null || sudo systemctl restart "$SERVICE"
  sleep 45
  code=$(probe); code="${code:-000}"
  if [ "$code" = "200" ]; then
    say "RECOVERED after restart"
  else
    say "ESCALATE still $code after restart — needs a human"
    fail=1
  fi
fi

# 2. Readiness endpoint (index reachable, vectors consistent)
hcode=$(curl -s -o /tmp/hc_health -w "%{http_code}" --max-time 25 "$BASE/health" || echo 000)
if [ "$hcode" != "200" ]; then
  say "ESCALATE /health returned $hcode: $(head -c 200 /tmp/hc_health 2>/dev/null)"
  fail=1
fi

# 3. Service unit state
if ! systemctl is-active --quiet "$SERVICE"; then
  say "ESCALATE $SERVICE is not active"
  fail=1
fi

# 4. Disk headroom
avail_gb=$(df -BG --output=avail "$DATA_DIR" 2>/dev/null | tail -1 | tr -dc '0-9')
if [ -n "${avail_gb:-}" ] && [ "$avail_gb" -lt "$DISK_MIN_GB" ]; then
  say "ESCALATE only ${avail_gb}GB free on the data volume"
  fail=1
fi

# 5. Did the nightly refresh run? Silent staleness looks healthy from outside.
if [ -f "$REFRESH_LOG" ]; then
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$REFRESH_LOG") ) / 3600 ))
  if [ "$age_h" -gt "$REFRESH_MAX_HOURS" ]; then
    say "ESCALATE refresh log is ${age_h}h old — the nightly job may be failing"
    fail=1
  fi
else
  say "WARN no refresh log yet at $REFRESH_LOG"
fi

[ "$fail" -eq 0 ] && say "ok  http=$code health=$hcode disk=${avail_gb:-?}GB"
exit "$fail"
