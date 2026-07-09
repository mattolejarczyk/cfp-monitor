#!/usr/bin/env bash
# One-shot VPS setup for the license proxy. Run as the `ubuntu` user, from inside the repo clone:
#   cd /home/ubuntu/.openclaw/workspace/cfp-proxy && bash scripts/vps_setup.sh
# Idempotent — safe to re-run after `git pull`. Does NOT touch .env (your key) or nginx (root).
set -euo pipefail
cd "$(dirname "$0")/.."          # repo root

echo "==> Python venv + proxy deps"
python3 -m venv venv
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet fastapi uvicorn litellm python-dotenv

echo "==> start.sh (loads .env, runs uvicorn on 127.0.0.1:8800)"
cat > start.sh <<'SH'
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
set -a; [ -f .env ] && . ./.env; set +a
exec venv/bin/python -m uvicorn licenseproxy.server:app --host 127.0.0.1 --port 8800
SH
chmod +x start.sh

echo
echo "Setup complete. Remaining (one time):"
echo "  1) Ensure .env has your real key:  nano .env   (OPENROUTER_API_KEY or OPENAI_API_KEY)"
echo "  2) Start under PM2:"
echo "       PM2_HOME=\$HOME/.pm2 pm2 start ./start.sh --name cfp-proxy && PM2_HOME=\$HOME/.pm2 pm2 save"
echo "  3) nginx route /cfp-proxy/ -> 127.0.0.1:8800 (needs sudo; see HANDOFF.md section 1)."
echo
echo "To update later:  git pull && PM2_HOME=\$HOME/.pm2 pm2 restart cfp-proxy"
