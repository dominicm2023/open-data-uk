# Deployment — UK Open Data Index on the existing VPS

Target: `ubuntu@$VPS_HOST` (the box already running groundwatercast).

**Read this before running anything.** That box serves a live site with real
users; every step below is designed to be additive and reversible, and the
rollback section undoes the whole thing in about a minute.

## Why this box fits

Measured 2026-08-13, app footprint vs. what's spare:

| | App needs | VPS has spare |
|---|---:|---:|
| RAM | 570 MB resident | 21 GB |
| Disk | ~1.6 GB (410 MB data + 1.1 GB venv + 88 MB model) | 150 GB |
| CPU | ~0.5 s of one core per query | 8 cores, load 0.00 |
| Bandwidth | ~2,500 link checks/night | 1.06 Gbit/s |

Nothing here is close to a limit. The two things worth being deliberate
about are **not disturbing groundwatercast's cron schedule** and **capping
our memory** so a bug in our service can never starve theirs.

## Decisions needed before starting

1. **DNS.** Hostname is `open-data.org.uk`; the A record doesn't
   exist yet and must be created in Cloudflare — see Step 5a for the
   proxied-vs-DNS-only choice.
2. **Whether to use sudo.** Steps 4–6 (systemd, Caddy, logrotate) need root.
   Everything else runs as `ubuntu`. If you'd rather avoid root entirely,
   see *Appendix: rootless variant*.

---

## Step 1 — Code and virtualenv

```bash
ssh ubuntu@$VPS_HOST
mkdir -p ~/opendata-index && cd ~/opendata-index
```

Copy the repo up from the laptop (run this **on the laptop**, from the
project directory):

```bash
scp -r *.py sources.yaml requirements.txt refresh.sh web scripts \
    ubuntu@$VPS_HOST:~/opendata-index/
```

Then, back on the VPS, build the venv. **Pin Python 3.13** — 3.14.4 is the
only system interpreter and PyTorch may not publish 3.14 wheels yet; `uv`
fetches a managed 3.13 automatically:

```bash
cd ~/opendata-index
~/.local/bin/uv venv --python 3.13

# CPU-only PyTorch FIRST — see the warning below
~/.local/bin/uv pip install --python .venv/bin/python \
    torch --index-url https://download.pytorch.org/whl/cpu

~/.local/bin/uv pip install --python .venv/bin/python -r requirements.txt
```

> ⚠️ **Install CPU-only torch first, or the venv balloons.** On Linux the
> default `torch` wheel drags in the whole CUDA stack — several GB of
> `nvidia-*` packages this box has no GPU to use. Installing from the CPU
> index first means the `sentence-transformers` dependency is already
> satisfied and the rest resolves around it. Measured on the box: **1.1 GB**
> this way, versus several GB with the default wheel. (Not an issue on the
> Windows dev machine, where the default wheel is already CPU-only — hence
> the trap.) Confirm with `.venv/bin/python -c "import torch; print(torch.__version__)"`
> — it should print a `+cpu` suffix.

Bake the embedding model into a local cache so the service never downloads
at query time (and so the systemd sandbox doesn't need access to `~/.cache`):

```bash
mkdir -p ~/opendata-index/model-cache
HF_HOME=~/opendata-index/model-cache .venv/bin/python -c \
  "from sentence_transformers import SentenceTransformer; \
   SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

**Verify:** `.venv/bin/python -c "import torch, sentence_transformers; print('ok')"`

---

## Step 2 — Ship the built index

The index is already built and link-checked on the laptop, so copy it up
rather than spending an hour rebuilding it on the box.

SQLite is in WAL mode, so **do not `scp index.db` directly** — a plain copy
can miss committed data still sitting in the `-wal` file. `VACUUM INTO`
writes a clean, consistent single-file snapshot (verified: all six tables
copy intact, and it defragments on the way, 325 MB → 311 MB).

On the **VPS**, make the target directory:

```bash
mkdir -p ~/opendata-index/data
```

On the **laptop**, snapshot and upload:

```bash
python -c "import sqlite3; sqlite3.connect('index.db').execute(\"VACUUM INTO 'index-snapshot.db'\")"
scp index-snapshot.db emb_keys.json embeddings.npy \
    ubuntu@$VPS_HOST:~/opendata-index/data/
rm index-snapshot.db
```

Back on the **VPS**, put it in place:

```bash
mv ~/opendata-index/data/index-snapshot.db ~/opendata-index/data/index.db
```

That's ~410 MB total (the snapshot is ~311 MB — `VACUUM INTO` defragments
as it copies — plus 95 MB of vectors). `DATA_DIR` points the app at this
directory; it's set in the systemd unit in Step 4.

**Verify:**

```bash
cd ~/opendata-index
DATA_DIR=~/opendata-index/data .venv/bin/python -c \
  "from paths import connect; c=connect(); \
   print(c.execute('select count(*) from datasets').fetchone()[0], 'datasets')"
```

---

## Step 3 — Smoke-test before installing any service

Run it in the foreground and confirm it answers, before wiring up systemd:

```bash
cd ~/opendata-index
DATA_DIR=~/opendata-index/data HF_HOME=~/opendata-index/model-cache \
  .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8010
```

From a second SSH session:

```bash
curl -s "http://127.0.0.1:8010/api/search?q=flood+risk&k=2" | head -c 400
curl -s "http://127.0.0.1:8010/api/stats"
```

Expect a JSON payload with `confidence`, `results`, and an `attribution`
field. Ctrl-C when satisfied. **If this doesn't work, stop here** — nothing
has been installed yet, so there is nothing to undo.

---

## Step 4 — systemd service

Port 8010 is bound to loopback only; Caddy is the only thing that reaches
it, so no firewall change is needed and nothing new is exposed publicly.

`sudo tee /etc/systemd/system/opendata-index.service` with:

```ini
[Unit]
Description=UK Open Data Index (search API + web UI)
After=network-online.target

[Service]
Type=exec
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/opendata-index
Environment=DATA_DIR=/home/ubuntu/opendata-index/data
Environment=HF_HOME=/home/ubuntu/opendata-index/model-cache
ExecStart=/home/ubuntu/opendata-index/.venv/bin/uvicorn server:app \
          --host 127.0.0.1 --port 8010 --no-proxy-headers
Restart=on-failure
RestartSec=10

# Hard ceiling: the app measures 570 MB, so 1.2 GB is generous headroom
# while still guaranteeing it can never crowd out groundwatercast.
MemoryMax=1200M
CPUWeight=50

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/ubuntu/opendata-index/data

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now opendata-index
systemctl status opendata-index --no-pager
```

**Verify:** `curl -s http://127.0.0.1:8010/api/stats` returns JSON, and
`systemctl show opendata-index -p MemoryCurrent` shows well under the cap.

> `ProtectHome=read-only` lets the service read its own code and model cache
> while making the rest of `/home` read-only to it — `ReadWritePaths` carves
> out the one directory it legitimately writes to.

> ⚠️ **`--no-proxy-headers` is load-bearing, not decoration.** uvicorn enables
> proxy-header handling *by default*, which silently rewrites
> `request.client` from `X-Forwarded-For` before any application code runs.
> Behind Cloudflare that yields a **different edge IP on every request**
> (172.64.x, 172.68.x, 172.70.x …), so the rate limiter files each request
> in its own bucket and never limits anything — verified: 40 rapid requests
> all returned 200. Disabling it restores the true peer (127.0.0.1), which
> is what `_client_ip()` in `server.py` checks before trusting
> `CF-Connecting-IP`. With the flag: 30 × 200 then 10 × 429, as intended.

---

## Step 5 — DNS and Caddy site

Hostname: **`open-data.org.uk`**.

### 5a. DNS

The domain is registered at OVH and its **nameservers point at Cloudflare**,
so all records live in the Cloudflare zone for `open-data.org.uk`. Two
records, both **proxied** (orange cloud):

| Name | Type | Value | Proxy |
|---|---|---|---|
| `open-data.org.uk` (apex, shown as `@`) | A | `<your-origin-ip>` | Proxied |
| `www` | A | `<your-origin-ip>` | Proxied |

Proxied hides the origin IP and gives DDoS protection and caching, matching
how groundwatercast.com is already served from this box. It only breaks if
Cloudflare's SSL mode is **Flexible** (redirect loop) — Full or Full (strict)
is required, which the existing apex already proves is set.

> **DNSSEC and nameserver changes don't mix.** If the registrar has DNSSEC
> enabled with DS records for the *old* nameservers, resolvers reject the
> zone once the nameservers change. Turn DNSSEC off at the registrar before
> the switch, then re-enable it from Cloudflare's side afterwards.

**Verify before continuing:** `dig +short open-data.org.uk` returns
addresses. Caddy cannot issue a certificate for a name that doesn't resolve,
so this must be done first.

> Certificate issuance can fail for a few minutes after a DNS change with
> *"During secondary validation: <old IP>"* — Let's Encrypt validates from
> several vantage points and one of them is still holding a stale answer.
> It clears itself; Caddy retries automatically.

### 5b. Caddy

Caddy 2.11.4 already owns :80/:443. Append a block to `/etc/caddy/Caddyfile`
(leave the existing groundwatercast blocks untouched):

```caddy
open-data.org.uk, www.open-data.org.uk {
	encode gzip
	reverse_proxy 127.0.0.1:8010
}
```

If the site previously answered on another hostname, don't just delete its
block — replace the body with a permanent redirect so existing links and
search results keep working:

```caddy
data.groundwatercast.com {
	redir https://open-data.org.uk{uri} permanent
}
```

> The app reads `CF-Connecting-IP` / `X-Forwarded-For` for rate limiting, so
> visitors are limited individually rather than all sharing one bucket —
> but only when the request arrives via loopback (i.e. through Caddy), so
> the headers can't be forged from outside. Caddy sets `X-Forwarded-For`
> automatically; no extra config needed.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile   # check BEFORE reloading
sudo systemctl reload caddy                          # reload, not restart
```

`validate` first and `reload` (not `restart`) matter here: a reload keeps
groundwatercast serving throughout, and a config error caught by `validate`
never reaches the running server.

**Verify:** `curl -sI https://open-data.org.uk` returns 200, and
groundwatercast.com still loads.

---

## Step 6 — Nightly refresh

groundwatercast's cron is busy from 21:30 through to noon, but **nothing
runs between 12:00 and 21:30 UTC**. 14:20 sits in that gap, and off the
hour to avoid the hourly `run_chain --live` job.

`crontab -e` as `ubuntu`, append:

```cron
20 14 * * * cd /home/ubuntu/opendata-index && DATA_DIR=/home/ubuntu/opendata-index/data HF_HOME=/home/ubuntu/opendata-index/model-cache bash refresh.sh >> /home/ubuntu/opendata-index/data/cron_refresh.log 2>&1
```

`refresh.sh` harvests, embeds new datasets, re-runs dedup, and link-checks a
rolling 2,500 URLs (8 workers) — so the whole index re-verifies roughly
monthly without a nightly spike. The server picks up new data on its next
query; **no restart is needed for data changes.**

Log rotation, `sudo tee /etc/logrotate.d/opendata-index`:

```
/home/ubuntu/opendata-index/data/cron_refresh.log {
	weekly
	rotate 8
	compress
	missingok
	notifempty
	copytruncate
}
```

**Verify:** run `bash refresh.sh` by hand once and read the output before
trusting it to cron.

---

## Rollback

Complete removal, in order:

```bash
crontab -e                                    # delete the 20 14 line
sudo systemctl disable --now opendata-index
sudo rm /etc/systemd/system/opendata-index.service /etc/logrotate.d/opendata-index
sudo systemctl daemon-reload
sudo nano /etc/caddy/Caddyfile                # delete the open-data.org.uk block
sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl reload caddy
rm -rf ~/opendata-index
```

Nothing above touches groundwatercast's files, venvs, cron entries, or its
Caddy blocks, so removing this service returns the box to exactly its
current state.

## Day-to-day

| Task | Command |
|---|---|
| Is it up? | `systemctl status opendata-index` |
| Logs | `journalctl -u opendata-index -n 50` |
| Refresh log | `tail -40 ~/opendata-index/data/cron_refresh.log` |
| Memory in use | `systemctl show opendata-index -p MemoryCurrent` |
| Deploy code change | `scp` the files, then `sudo systemctl restart opendata-index` |
| Add a data source | edit `sources.yaml`, then `DATA_DIR=~/opendata-index/data .venv/bin/python harvester.py --source <id>` |

> ⚠️ **Always set `DATA_DIR` when running anything by hand on the box.**
> Without it `paths.py` falls back to the repo root, and SQLite *silently
> creates a new empty `index.db`* there rather than failing — so the script
> appears to work while reading and writing the wrong (empty) database. If
> you ever see `no such table`, this is why: delete the stray
> `~/opendata-index/index.db` and re-run with `DATA_DIR` set. `refresh.sh`
> via cron already sets it.

## Appendix: rootless variant

To avoid sudo entirely, run the service as a **user unit** instead of Steps
4–6's system unit: put the same file (minus `User=`/`Group=`) in
`~/.config/systemd/user/opendata-index.service`, then:

```bash
loginctl enable-linger ubuntu     # keeps it running when logged out
systemctl --user daemon-reload
systemctl --user enable --now opendata-index
```

Caddy still needs a root-owned config edit, so this only removes two of the
three sudo touchpoints — unless you front it with something else entirely.
