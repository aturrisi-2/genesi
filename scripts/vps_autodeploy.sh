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

ensure_fetch_head_writable() {
  if [[ ! -e "$APP_DIR/.git/FETCH_HEAD" || -w "$APP_DIR/.git/FETCH_HEAD" ]]; then
    return 0
  fi

  log "Detected non-writable .git/FETCH_HEAD; attempting cleanup"
  rm -f "$APP_DIR/.git/FETCH_HEAD" 2>/dev/null || true

  if [[ ! -e "$APP_DIR/.git/FETCH_HEAD" || -w "$APP_DIR/.git/FETCH_HEAD" ]]; then
    return 0
  fi

  log "FETCH_HEAD still not writable; attempting ownership repair"
  repair_repo_ownership || true
}

log "Starting VPS deploy"
cd "$APP_DIR"

ensure_repo_writable
ensure_fetch_head_writable

log "Fetching latest code from origin/$BRANCH"
if ! git fetch origin; then
  log "git fetch failed; retrying without FETCH_HEAD write"
  if git fetch --no-write-fetch-head origin; then
    :
  else
    log "fallback fetch failed; attempting ownership repair and retry"
    repair_repo_ownership || true
    ensure_fetch_head_writable
    git fetch --no-write-fetch-head origin
  fi
fi

if ! git rev-parse --verify "origin/$BRANCH" >/dev/null 2>&1; then
  log "ERROR: remote ref origin/$BRANCH not available after fetch"
  repair_repo_ownership || true
  exit 1
fi

git checkout "$BRANCH"
if ! git reset --hard "origin/$BRANCH"; then
  log "git reset --hard failed; attempting ownership repair and retry"
  repair_repo_ownership || true
  git reset --hard "origin/$BRANCH"
fi
# static/ig_posts: media pubblicati su Instagram (IG li scarica dal nostro URL
# anche minuti dopo la publish) — MAI cancellarli col clean.
# static/voice_test: campioni vocali. memory/: stato runtime (profili, episodi).
git clean -fd -e .venv/ -e data/ -e logs/ -e memory/ -e static/ig_posts/ -e static/voice_test/

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


# ── Diagnostics token: genera LIVE_LOGS_TOKEN se assente ─────────────────────
# Usato dall'endpoint /api/system/live-logs per lettura log remota senza SSH.
_ENV_FILE="$APP_DIR/.env"
if [[ -f "$_ENV_FILE" ]] && ! grep -q "^LIVE_LOGS_TOKEN=" "$_ENV_FILE"; then
  if command -v openssl >/dev/null 2>&1; then
    _NEW_TOKEN="$(openssl rand -hex 32)"
  else
    _NEW_TOKEN="$(head -c 32 /dev/urandom | xxd -p | tr -d '\n')"
  fi
  echo "LIVE_LOGS_TOKEN=$_NEW_TOKEN" >> "$_ENV_FILE"
  log "LIVE_LOGS_TOKEN generated and added to .env"
  # SECURITY: non stampare mai il valore del token nei log (finiscono in GitHub Actions).
  log "DIAG: LIVE_LOGS_TOKEN present=yes (len=${#_NEW_TOKEN})"
  # Scrivi anche nel file di bootstrap (memory/ è esclusa da git clean)
  mkdir -p "$APP_DIR/memory"
  echo "$_NEW_TOKEN" > "$APP_DIR/memory/.live_logs_token"
  chmod 600 "$APP_DIR/memory/.live_logs_token"
elif [[ -f "$_ENV_FILE" ]]; then
  _EXISTING_TOKEN="$(grep "^LIVE_LOGS_TOKEN=" "$_ENV_FILE" | cut -d= -f2 | head -1)"
  if [[ -n "$_EXISTING_TOKEN" ]]; then
    mkdir -p "$APP_DIR/memory"
    echo "$_EXISTING_TOKEN" > "$APP_DIR/memory/.live_logs_token"
    chmod 600 "$APP_DIR/memory/.live_logs_token"
    # SECURITY: non stampare mai il valore del token nei log.
    log "DIAG: LIVE_LOGS_TOKEN present=yes (len=${#_EXISTING_TOKEN})"
  fi
fi
unset _ENV_FILE _NEW_TOKEN _EXISTING_TOKEN

log "Restarting service: $SERVICE_NAME"
SERVICE_CHECK_INTERVAL_SECONDS="${SERVICE_CHECK_INTERVAL_SECONDS:-2}"
SERVICE_CHECK_MAX_ATTEMPTS="${SERVICE_CHECK_MAX_ATTEMPTS:-15}"

if [[ "$(id -u)" -eq 0 ]]; then
  systemctl restart "$SERVICE_NAME"
  ACTIVE_RC=1
  for ((attempt = 1; attempt <= SERVICE_CHECK_MAX_ATTEMPTS; attempt++)); do
    if systemctl is-active "$SERVICE_NAME" >/dev/null 2>&1; then
      ACTIVE_RC=0
      break
    fi
    sleep "$SERVICE_CHECK_INTERVAL_SECONDS"
  done

  if [[ "$ACTIVE_RC" -ne 0 ]]; then
    log "ERROR: service $SERVICE_NAME is not active after restart"
    systemctl is-active "$SERVICE_NAME" || true
    exit 1
  fi
else
  SYSTEMCTL_BIN="$(command -v systemctl || echo /bin/systemctl)"
  RESTART_RC=0
  sudo -n "$SYSTEMCTL_BIN" restart "$SERVICE_NAME" >/dev/null 2>&1 || RESTART_RC=$?

  if [[ "$RESTART_RC" -eq 0 ]]; then
    ACTIVE_RC=1
    for ((attempt = 1; attempt <= SERVICE_CHECK_MAX_ATTEMPTS; attempt++)); do
      if "$SYSTEMCTL_BIN" is-active "$SERVICE_NAME" >/dev/null 2>&1; then
        ACTIVE_RC=0
        break
      fi
      sleep "$SERVICE_CHECK_INTERVAL_SECONDS"
    done

    if [[ "$ACTIVE_RC" -ne 0 ]]; then
      log "ERROR: service $SERVICE_NAME is not active after restart"
      "$SYSTEMCTL_BIN" is-active "$SERVICE_NAME" || true
      exit 1
    fi
  else
    log "ERROR: passwordless sudo is required to restart $SERVICE_NAME"
    log "Add a sudoers rule for the deploy user, for example:"
    log "  <deploy-user> ALL=(root) NOPASSWD: /bin/systemctl restart $SERVICE_NAME, /bin/systemctl is-active $SERVICE_NAME, /usr/bin/systemctl restart $SERVICE_NAME, /usr/bin/systemctl is-active $SERVICE_NAME"
    exit 1
  fi
fi

log "Deploy completed successfully"
