# Operator cheat-sheet — license proxy (live)

**Live endpoint:** https://channeled.org/cfp-proxy
**On the VPS:** SSH in as `ubuntu`, then `cd /home/ubuntu/.openclaw/workspace/cfp-proxy`
Most `admin` commands need the env loaded first: `set -a; . ./.env; set +a`

## Daily commands (from the app dir, env sourced)
```bash
PFX="set -a; . ./.env; set +a; venv/bin/python -m licenseproxy.admin"

# Issue a customer key
bash -c "$PFX issue --customer 'Customer Name' --plan pro --quota 20000000"

# KILL SWITCH — stops their crawling on the next call
bash -c "$PFX revoke <key>"

# Restore
bash -c "$PFX reactivate <key>"

# Billing / usage
bash -c "$PFX usage <key>"      # raw tokens for one customer
bash -c "$PFX list"             # all keys + state
# Monthly invoice readout (per-customer tokens + $ at your cost/price per MILLION tokens):
bash -c "$PFX billing --period 2026-07 --rate 0.14"
bash -c "$PFX billing --period 2026-07 --rate 0.14 --csv > invoice-2026-07.csv"

# Force-upgrade old client versions (refuse below floor)
bash -c "$PFX floor <key> 1.3.0"

# Adjust / reset a token quota (e.g. at monthly billing)
bash -c "$PFX quota <key> 20000000 --reset-used"
```

## Service management (PM2, as ubuntu)
```bash
PM2_HOME=/home/ubuntu/.pm2 pm2 restart cfp-proxy     # after editing .env
PM2_HOME=/home/ubuntu/.pm2 pm2 logs cfp-proxy --lines 30 --nostream
PM2_HOME=/home/ubuntu/.pm2 pm2 list
```
Survives reboots via the existing `pm2-ubuntu.service` (already `pm2 save`d).

## Health checks
```bash
curl -s -m 8  -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer test" http://127.0.0.1:8800/v1/license   # 401 = app up
curl -s -m 12 -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <key>" https://channeled.org/cfp-proxy/v1/license  # 200 = active
```

## Backups (do this once)
Weekly online backup of `licenses.db`, keeping 8 weeks (script is in the repo):
```bash
# install the weekly cron (Sunday 03:00) as the ubuntu user:
( crontab -l 2>/dev/null; echo "0 3 * * 0 /home/ubuntu/.openclaw/workspace/cfp-proxy/scripts/backup_licenses.sh >> /home/ubuntu/.openclaw/workspace/cfp-proxy/backups/backup.log 2>&1" ) | crontab -
# run once now to verify:
bash /home/ubuntu/.openclaw/workspace/cfp-proxy/scripts/backup_licenses.sh
```
Backups land in `…/cfp-proxy/backups/licenses-YYYY-MM-DD.db`. To restore: stop the proxy, copy a
backup over `licenses.db`, restart.

## Where things live
- App: `/home/ubuntu/.openclaw/workspace/cfp-proxy` (git clone; `git pull` to update, then restart)
- Vendor key + config: `.env` (chmod 600 — the ONLY place the LLM key lives)
- License DB: `licenses.db` — **back this up** (it holds every key + usage)
- nginx route: `/etc/nginx/sites-available/channeled.org` → `location /cfp-proxy/` → `127.0.0.1:8800`

## Switch LLM provider (OpenAI vs OpenRouter)
Edit `.env`: set `PROXY_MODEL` (e.g. `openai/gpt-4o-mini` or `openrouter/deepseek/deepseek-chat`)
and the matching key (`OPENAI_API_KEY` / `OPENROUTER_API_KEY`), then `pm2 restart cfp-proxy`.

## Customer build (their machine)
`.env` gets only these — no LLM key:
```
CFP_LLM_PROXY_URL=https://channeled.org/cfp-proxy
CFP_LICENSE_KEY=cfp_theirkey
```
