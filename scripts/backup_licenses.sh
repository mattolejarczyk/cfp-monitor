#!/usr/bin/env bash
# Weekly backup of the license DB (holds every customer key + usage). Run as `ubuntu`.
# Uses SQLite's online .backup so it's safe even while the proxy is serving. Keeps 8 weeks.
set -euo pipefail
APP="${APP:-/home/ubuntu/.openclaw/workspace/cfp-proxy}"
DB="$APP/licenses.db"
BK="$APP/backups"
mkdir -p "$BK"

STAMP="$(date +%F)"
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "$DB" ".backup '$BK/licenses-$STAMP.db'"
else
  cp -f "$DB" "$BK/licenses-$STAMP.db"     # fallback if sqlite3 CLI isn't installed
fi

# Retain the 8 most recent, delete older.
ls -1t "$BK"/licenses-*.db 2>/dev/null | tail -n +9 | xargs -r rm -f
echo "$(date -Is)  backed up -> $BK/licenses-$STAMP.db"
