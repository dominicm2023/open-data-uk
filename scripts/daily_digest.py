"""Daily health digest for the UK Open Data Index, emailed from the VPS.

The box tells you when something needs attention, instead of you checking.
The verdict is in the subject line, so a green subject can be deleted
unread and only amber or red needs opening.

What it watches is chosen from what has actually gone wrong here, not from
a generic checklist:

  * A nightly refresh that silently stopped running. A Windows line-ending
    in refresh.sh once killed it for three nights and nothing said so — the
    site looked perfectly healthy while the data went stale.
  * A refresh that ran but threw: tracebacks in the log, source feeds that
    failed, sources that yielded nothing, IndexNow rejections.
  * The index shrinking. Ghost-reaping and junk-title removal are meant to
    remove records, but a large unexplained fall is how a bad harvest
    announces itself.
  * The service being up but not answering a real query, which is the
    failure a process check misses entirely.

SMTP config is read from ``~/.opendata-mail.env``, falling back to
``~/.gwc-mail.env`` (KEY=value lines, mode 600, never committed).

Run on the box from the repo root:
    .venv/bin/python scripts/daily_digest.py --print   # render, send nothing
    .venv/bin/python scripts/daily_digest.py           # gather and email

Cron (08:00 UK, DST-safe via CRON_TZ):
    CRON_TZ=Europe/London
    0 8 * * *  cd ~/opendata-index && DATA_DIR=/home/ubuntu/opendata-index/data
               .venv/bin/python scripts/daily_digest.py >> data/cron_digest.log 2>&1
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
import urllib.request
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

SERVICE = "opendata-index"
BASE = "http://127.0.0.1:8010"
SMTP_HOST_DEFAULT = "ssl0.ovh.net"
SMTP_PORT_DEFAULT = "587"
MAIL_ENVS = (Path.home() / ".opendata-mail.env", Path.home() / ".gwc-mail.env")

REFRESH_MAX_HOURS = 36     # nightly, so past this it has missed one
DISK_MIN_GB = 10
INDEX_DROP_ALERT = 0.02    # a fall past 2% overnight wants explaining

GREEN, AMBER, RED = "green", "amber", "red"
RANK = {GREEN: 0, AMBER: 1, RED: 2}
ICON = {GREEN: "OK", AMBER: "WARN", RED: "FAIL"}
COLOUR = {GREEN: "#0a6b45", AMBER: "#7a5c00", RED: "#a4192b"}


class Report:
    """Findings, each with a severity, in the order they were gathered."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, str, str]] = []

    def add(self, level: str, label: str, detail: str = "") -> None:
        self.lines.append((level, label, detail))

    @property
    def verdict(self) -> str:
        return max((lv for lv, _, _ in self.lines),
                   key=lambda v: RANK[v], default=GREEN)

    def of(self, level: str) -> list[tuple[str, str, str]]:
        return [x for x in self.lines if x[0] == level]


def sh(cmd: list[str], timeout: int = 20) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def http(path: str, timeout: int = 25) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
            return r.status, r.read(20000).decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)[:120]


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", ROOT))


def _first_match(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(0)[:160] if m else ""


# --- the checks ---------------------------------------------------------

def check_service(rep: Report) -> None:
    state = sh(["systemctl", "is-active", SERVICE]) or "unknown"
    if state != "active":
        rep.add(RED, "Service is not running", f"systemctl says {state}")
        return
    since = sh(["systemctl", "show", SERVICE, "-p",
                "ActiveEnterTimestamp", "--value"])
    rep.add(GREEN, "Service running", f"since {since or 'unknown'}")


def check_site(rep: Report) -> None:
    """Answering a real query, not merely listening on a port."""
    code, body = http("/api/search?q=flood+risk&k=3")
    if code != 200:
        rep.add(RED, "Search is not answering", f"HTTP {code} - {body[:80]}")
    else:
        try:
            n = len(json.loads(body).get("results", []))
            rep.add(GREEN if n else AMBER, f"Search answering, {n} results")
        except ValueError:
            rep.add(RED, "Search returned unparseable JSON")
    for path in ("/", "/about", "/publishers", "/findings"):
        code, _ = http(path)
        if code != 200:
            rep.add(RED, f"Page {path} returned HTTP {code}")


def _refresh_text(log: Path) -> str:
    """The refresh log, reaching into the rotated copy when today's is empty."""
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    if "=====REFRESH-RUN=====" in text:
        return text
    for old in sorted(log.parent.glob("cron_refresh.log.1*")):
        try:
            raw = old.read_bytes()
            if old.suffix == ".gz":
                import gzip
                raw = gzip.decompress(raw)
            return raw.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            continue
    return text


def check_refresh(rep: Report, state: dict) -> dict:
    """Did the nightly job run, finish, and finish cleanly?"""
    out: dict = {}
    text = _refresh_text(data_dir() / "cron_refresh.log")
    runs = re.findall(r"=====REFRESH-RUN===== (\S+)", text)
    dones = re.findall(r"=====REFRESH-DONE===== (\S+)", text)
    if not runs:
        rep.add(RED, "No refresh has ever been recorded")
        return out

    last = runs[-1]
    out["last_run"] = last
    age_h = None
    try:
        started = dt.datetime.fromisoformat(last)
        age_h = (dt.datetime.now(started.tzinfo) - started).total_seconds() / 3600
    except ValueError:
        pass

    if age_h is not None and age_h > REFRESH_MAX_HOURS:
        rep.add(RED, "The nightly refresh has not run",
                f"last started {last}, {age_h:.0f} hours ago")
    elif len(dones) < len(runs):
        # A refresh takes about an hour. Inside that window it is running,
        # not broken — only past it has it actually died, and calling a
        # healthy job a failure is how a monitor teaches you to ignore it.
        if age_h is not None and age_h < 3:
            rep.add(GREEN, "Refresh is still running",
                    f"started {last}, {age_h:.1f}h ago")
        else:
            rep.add(RED, "The last refresh started but never finished", last)
    else:
        rep.add(GREEN, "Refresh completed",
                last + (f", {age_h:.0f}h ago" if age_h is not None else ""))

    tail = text.rsplit("=====REFRESH-RUN=====", 1)[-1]
    if tracebacks := tail.count("Traceback (most recent call last)"):
        rep.add(RED, f"{tracebacks} traceback(s) in the last refresh",
                _first_match(tail, r"^\w*Error:.*$"))
    if failed := re.findall(r"^\[(\S+)\] feed failed", tail, re.M):
        rep.add(AMBER, f"{len(failed)} source feed(s) failed",
                ", ".join(failed[:6]))
    if m := re.search(r"WARNING: \d+ source\(s\) hold zero datasets: (.+)", tail):
        out["zero_sources"] = sorted(s.strip() for s in m.group(1).split(","))
        known = set(state.get("zero_sources") or [])
        new = [s for s in out["zero_sources"] if s not in known]
        rep.add(AMBER if new else GREEN,
                f"{len(out['zero_sources'])} source(s) yield nothing",
                ("newly silent: " + ", ".join(new)) if new
                else "unchanged from yesterday")
    if reaped := re.findall(r"\] reaped (\d+) ghosts", tail):
        out["reaped"] = sum(int(n) for n in reaped)
        rep.add(GREEN, f"{out['reaped']:,} ghost record(s) reaped",
                "records their portal no longer lists")
    if m := re.search(r"([\d,]+) licences recovered from a merged twin", tail):
        out["inherited"] = int(m.group(1).replace(",", ""))
    if "-> HTTP 200" in tail or "-> HTTP 202" in tail:
        rep.add(GREEN, "IndexNow accepted the changed URLs")
    elif m := re.search(r"indexnow.*-> HTTP (\d+)", tail):
        rep.add(AMBER, f"IndexNow returned HTTP {m.group(1)}")
    return out


def check_index(rep: Report, state: dict) -> dict:
    """Counts, and how they moved. A big unexplained fall is the alarm."""
    out: dict = {}
    try:
        from paths import connect
        conn = connect()
    except Exception as exc:  # noqa: BLE001
        rep.add(RED, "Cannot open the index", f"{type(exc).__name__}: {exc}")
        return out
    try:
        out["datasets"] = conn.execute(
            "SELECT COUNT(*) FROM datasets").fetchone()[0]
        out["publishers"] = conn.execute(
            "SELECT COUNT(DISTINCT publisher) FROM datasets "
            "WHERE publisher IS NOT NULL").fetchone()[0]
        for name, sql in (("duplicates", "SELECT COUNT(*) FROM duplicates"),
                          ("inherited_total",
                           "SELECT COUNT(*) FROM license_inherited")):
            try:
                out[name] = conn.execute(sql).fetchone()[0]
            except Exception:  # noqa: BLE001
                pass
        avail = dict(conn.execute(
            "SELECT availability, COUNT(*) FROM datasets GROUP BY 1").fetchall())
        checked = sum(v for k, v in avail.items() if k)
        out["checked_pct"] = round(100 * checked / max(out["datasets"], 1))
    finally:
        conn.close()

    was = state.get("datasets")
    delta = out["datasets"] - was if was else 0
    if was and delta < -was * INDEX_DROP_ALERT:
        rep.add(AMBER, f"The index shrank by {abs(delta):,} overnight",
                f"{was:,} to {out['datasets']:,} - expected if a big source "
                "was reaped, worth a look otherwise")
    else:
        sign = f"+{delta:,}" if delta >= 0 else f"{delta:,}"
        rep.add(GREEN, f"{out['datasets']:,} datasets, {sign} overnight",
                f"{out['publishers']:,} publishers, "
                f"{out['checked_pct']}% link-checked")
    return out


def check_box(rep: Report) -> dict:
    out: dict = {}
    total, _used, free = shutil.disk_usage("/")
    out["free_gb"] = round(free / 1e9)
    if out["free_gb"] < DISK_MIN_GB:
        rep.add(RED, f"Only {out['free_gb']} GB disk free")
    else:
        rep.add(GREEN, f"{out['free_gb']} GB disk free",
                f"of {round(total / 1e9)} GB")
    if m := re.search(r"Mem:\s+(\d+)\s+(\d+)", sh(["free", "-m"])):
        tot_m, used_m = int(m.group(1)), int(m.group(2))
        out["mem_pct"] = round(100 * used_m / tot_m)
        rep.add(AMBER if out["mem_pct"] > 85 else GREEN,
                f"Memory {out['mem_pct']}% used",
                f"{used_m:,} MB of {tot_m:,} MB")
    errs = sh(["journalctl", "-u", SERVICE, "--since", "24 hours ago",
               "-p", "err", "--no-pager", "-q"])
    bad = [ln for ln in errs.splitlines() if ln.strip()]
    if bad:
        rep.add(AMBER, f"{len(bad)} service error(s) in the journal today",
                bad[-1][:140])
    return out


def check_healthlog(rep: Report) -> None:
    """What the five-minute checker itself found over the last day."""
    log = data_dir() / "health.log"
    if not log.exists():
        rep.add(AMBER, "No health.log - is the 5-minute check installed?")
        return
    cutoff = (dt.datetime.now(dt.timezone.utc)
              - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H")
    recent = [ln for ln in log.read_text(encoding="utf-8", errors="replace")
              .splitlines()[-2000:] if ln[:13] >= cutoff]
    fails = [ln for ln in recent if "FAIL" in ln]
    if fails:
        rep.add(AMBER, f"{len(fails)} failed health check(s) in 24h",
                fails[-1][:140])
    else:
        rep.add(GREEN, f"{len(recent)} health checks in 24h, all passing")


def check_traffic(rep: Report) -> dict:
    out: dict = {}
    db = data_dir() / "queries.db"
    if not db.exists():
        return out
    try:
        import sqlite3
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        since = (dt.datetime.now(dt.timezone.utc)
                 - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        rows = conn.execute(
            "SELECT query, COUNT(*) FROM queries WHERE ts >= ? "
            "AND query != 'health check' GROUP BY query ORDER BY 2 DESC",
            (since,)).fetchall()
        conn.close()
    except Exception:  # noqa: BLE001
        return out
    out["searches"] = sum(n for _, n in rows)
    rep.add(GREEN, f"{out['searches']:,} real searches in 24h",
            ", ".join(q for q, _ in rows[:5]) if rows else "none")
    return out


# --- rendering ----------------------------------------------------------

def _esc(s: object) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def render_text(rep: Report) -> str:
    out = ["UK Open Data Index - daily digest",
           dt.datetime.now().strftime("%A %d %B %Y, %H:%M"),
           "", f"VERDICT: {rep.verdict.upper()}", ""]
    for level in (RED, AMBER, GREEN):
        for _, label, detail in rep.of(level):
            out.append(f"  [{ICON[level]:>4}] {label}")
            if detail:
                out.append(f"         {detail}")
    out += ["", "https://open-data.org.uk"]
    return "\n".join(out)


def render_html(rep: Report) -> str:
    rows = []
    for level in (RED, AMBER, GREEN):
        for _, label, detail in rep.of(level):
            sub = (f'<br><span style="color:#61656d;font-size:13px">'
                   f'{_esc(detail)}</span>' if detail else "")
            rows.append(
                f'<tr><td style="padding:6px 10px;color:{COLOUR[level]};'
                f'font-weight:600;white-space:nowrap;vertical-align:top">'
                f'{ICON[level]}</td>'
                f'<td style="padding:6px 10px"><b>{_esc(label)}</b>{sub}</td></tr>')
    v = rep.verdict
    return (
        '<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        'max-width:640px;color:#16181c">'
        '<h2 style="margin:0 0 2px">UK Open Data Index</h2>'
        f'<p style="margin:0 0 14px;color:#61656d;font-size:14px">'
        f'{dt.datetime.now().strftime("%A %d %B %Y, %H:%M")}</p>'
        f'<p style="margin:0 0 16px"><span style="background:{COLOUR[v]};'
        'color:#fff;padding:4px 12px;border-radius:12px;font-weight:600">'
        f'{v.upper()}</span></p>'
        '<table style="border-collapse:collapse;width:100%;font-size:14px">'
        f'{"".join(rows)}</table>'
        '<p style="margin:18px 0 0;font-size:13px;color:#61656d">'
        '<a href="https://open-data.org.uk" style="color:#14549c">'
        'open-data.org.uk</a> &middot; sent from the VPS by '
        'scripts/daily_digest.py</p></div>')


# --- delivery -----------------------------------------------------------

def read_env() -> dict:
    for path in MAIL_ENVS:
        if path.exists():
            out = {"_path": str(path)}
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
            return out
    return {}


def send(subject: str, text: str, html: str, env: dict) -> None:
    host = env.get("SMTP_HOST") or SMTP_HOST_DEFAULT
    port = int(env.get("SMTP_PORT") or SMTP_PORT_DEFAULT)
    user, pw, to = env.get("SMTP_USER"), env.get("SMTP_PASS"), env.get("MAIL_TO")
    if not (user and pw and to):
        where = env.get("_path") or " or ".join(str(p) for p in MAIL_ENVS)
        raise SystemExit(f"missing SMTP_USER / SMTP_PASS / MAIL_TO in {where}")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env.get("MAIL_FROM") or user
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(user, pw)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", dest="dry", action="store_true",
                    help="render to stdout and send nothing")
    args = ap.parse_args()

    state_path = data_dir() / "digest_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        state = {}

    rep, facts = Report(), {}
    # Each check is isolated. A digest that dies half-built tells you less
    # than one that reports the parts it could reach.
    for fn in (check_service, check_site, check_healthlog):
        try:
            fn(rep)
        except Exception as exc:  # noqa: BLE001
            rep.add(AMBER, f"Check {fn.__name__} failed",
                    f"{type(exc).__name__}: {exc}")
    for fn2 in (check_refresh, check_index):
        try:
            facts.update(fn2(rep, state) or {})
        except Exception as exc:  # noqa: BLE001
            rep.add(AMBER, f"Check {fn2.__name__} failed",
                    f"{type(exc).__name__}: {exc}")
    for fn3 in (check_box, check_traffic):
        try:
            facts.update(fn3(rep) or {})
        except Exception as exc:  # noqa: BLE001
            rep.add(AMBER, f"Check {fn3.__name__} failed",
                    f"{type(exc).__name__}: {exc}")

    v = rep.verdict
    n_bad = len(rep.of(RED)) + len(rep.of(AMBER))
    subject = f"[{v}] Open Data Index - " + (
        f"{facts.get('datasets', 0):,} datasets, all well" if v == GREEN
        else f"{n_bad} thing(s) need a look")

    if args.dry:
        print(subject)
        print()
        print(render_text(rep))
        return 0

    send(subject, render_text(rep), render_html(rep), read_env())
    print(f"{dt.datetime.now():%Y-%m-%dT%H:%M:%S} sent: {subject}")
    try:
        state_path.write_text(json.dumps(facts), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        # Never let the monitor be the thing that wakes you at 3am.
        print(f"daily_digest: {type(exc).__name__}: {exc}")
        sys.exit(0)
