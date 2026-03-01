#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/genesi}"
BRANCH="${BRANCH:-gold-faro-stable}"
SERVICE_NAME="${SERVICE_NAME:-genesi}"
VENV_DIR="${VENV_DIR:-$APP_DIR/.venv}"
AUTO_FIX_OWNERSHIP="${AUTO_FIX_OWNERSHIP:-1}"

log() {
  printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

repair_repo_ownership() {
  if [[ "$AUTO_FIX_OWNERSHIP" != "1" ]]; then
    return 1
  fi

  if ! command -v sudo >/dev/null 2>&1; then
    log "Ownership auto-fix skipped: sudo not available"
    return 1
  fi

  if ! sudo -n true 2>/dev/null; then
    log "Ownership auto-fix skipped: sudo requires password"
    return 1
  fi

  local current_user current_group
  current_user="$(id -un)"
  current_group="$(id -gn)"

  log "Repairing ownership for git metadata and tracked files as $current_user:$current_group"
  sudo -n chown -R "$current_user:$current_group" "$APP_DIR/.git"
  git ls-files -z | xargs -0 -r sudo -n chown "$current_user:$current_group"
  return 0
}

ensure_repo_writable() {
  if [[ -w "$APP_DIR/.git" && -w "$APP_DIR" ]]; then
    return 0
  fi

  log "Detected non-writable repo paths; attempting ownership repair"
  if ! repair_repo_ownership; then
    log "ERROR: repository is not writable and ownership repair failed"
    ls -ld "$APP_DIR" "$APP_DIR/.git" || true
    exit 1
  fi
}

log "Starting VPS deploy"
cd "$APP_DIR"

ensure_repo_writable

log "Fetching latest code from origin/$BRANCH"
if ! git fetch origin; then
  log "git fetch failed; attempting ownership repair and retry"
  repair_repo_ownership || true
  git fetch origin
fi

git checkout "$BRANCH"
if ! git reset --hard "origin/$BRANCH"; then
  log "git reset --hard failed; attempting ownership repair and retry"
  repair_repo_ownership || true
  git reset --hard "origin/$BRANCH"
fi
git clean -fd -e .venv/ -e data/ -e logs/

if [[ -f requirements.txt ]]; then
  log "Syncing Python dependencies"
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    log "Creating virtualenv at $VENV_DIR"
    rm -rf "$VENV_DIR"
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
