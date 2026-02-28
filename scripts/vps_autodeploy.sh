#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/genesi}"
BRANCH="${BRANCH:-gold-faro-stable}"
SERVICE_NAME="${SERVICE_NAME:-genesi}"

log() {
  printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "Starting VPS deploy"
cd "$APP_DIR"

log "Fetching latest code from origin/$BRANCH"
git fetch origin

git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

if [[ -f requirements.txt ]]; then
  log "Syncing Python dependencies"
  python3 -m pip install --upgrade pip
  python3 -m pip install -r requirements.txt
fi

log "Restarting service: $SERVICE_NAME"
if sudo -n true 2>/dev/null; then
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl is-active --quiet "$SERVICE_NAME"
else
  systemctl restart "$SERVICE_NAME"
  systemctl is-active --quiet "$SERVICE_NAME"
fi

log "Deploy completed successfully"
