#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/genesi}"
BRANCH="${BRANCH:-gold-faro-stable}"
SERVICE_NAME="${SERVICE_NAME:-genesi}"
VENV_DIR="${VENV_DIR:-$APP_DIR/.venv}"

log() {
  printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

log "Starting VPS deploy"
cd "$APP_DIR"

log "Fetching latest code from origin/$BRANCH"
git fetch origin

git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"
git clean -fd

if [[ -f requirements.txt ]]; then
  log "Syncing Python dependencies"
  if [[ ! -d "$VENV_DIR" ]]; then
    log "Creating virtualenv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
  fi

  "$VENV_DIR/bin/python" -m pip install --upgrade pip
  "$VENV_DIR/bin/pip" install -r requirements.txt
fi

log "Restarting service: $SERVICE_NAME"
if sudo -n systemctl restart "$SERVICE_NAME" 2>/dev/null; then
  sudo -n systemctl is-active "$SERVICE_NAME" >/dev/null
else
  systemctl restart "$SERVICE_NAME"
  systemctl is-active --quiet "$SERVICE_NAME"
fi

log "Deploy completed successfully"
