#!/usr/bin/env bash
# ============================================================
# setup_widget_core_vps.sh
# Setup INIZIALE dell'istanza Genesi Widget Core su VPS.
# Da eseguire UNA SOLA VOLTA come root (o con sudo).
#
# Cosa fa:
#   1. Clona il repo genesi in /opt/genesi-widget/ (branch cplace-stable)
#   2. Crea il virtualenv e installa le dipendenze
#   3. Copia /etc/genesi.env → /etc/genesi-widget-core.env (porta 8002)
#   4. Installa e avvia genesi-widget-core.service
#   5. Aggiunge sudoers per il deploy user
#
# Uso:
#   sudo bash scripts/setup_widget_core_vps.sh
# ============================================================
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/aturrisi-2/genesi.git}"
BRANCH="cplace-stable"
INSTALL_DIR="/opt/genesi-widget"
SERVICE_NAME="genesi-widget-core"
ENV_SOURCE="/etc/genesi.env"
ENV_DEST="/etc/genesi-widget-core.env"
SERVICE_SRC="/opt/genesi/config/genesi-widget-core.service"
DEPLOY_USER="${DEPLOY_USER:-luca}"  # utente che esegue i deploy (GitHub Actions SSH user)

log() { printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# ── 1. Clona repo ─────────────────────────────────────────────────────────────
log "Clono il repo in $INSTALL_DIR (branch: $BRANCH)"
if [[ -d "$INSTALL_DIR/.git" ]]; then
    log "Directory già esistente — aggiorno"
    cd "$INSTALL_DIR"
    git fetch origin
    git checkout "$BRANCH"
    git reset --hard "origin/$BRANCH"
else
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi
chown -R genesi:genesi "$INSTALL_DIR"

# ── 2. Virtualenv + dipendenze ────────────────────────────────────────────────
log "Creo virtualenv e installo dipendenze"
VENV="$INSTALL_DIR/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
    sudo -u genesi python3 -m venv "$VENV"
fi
sudo -u genesi "$VENV/bin/python" -m pip install --upgrade pip
sudo -u genesi "$VENV/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# ── 3. Crea directory runtime ─────────────────────────────────────────────────
log "Creo directory data/logs/memory"
for d in data logs memory; do
    mkdir -p "$INSTALL_DIR/$d"
    chown genesi:genesi "$INSTALL_DIR/$d"
done

# ── 4. File env ───────────────────────────────────────────────────────────────
log "Creo $ENV_DEST"
if [[ -f "$ENV_SOURCE" ]]; then
    cp "$ENV_SOURCE" "$ENV_DEST"
    # Cambia la porta a 8002 (sovrascrive PORT se presente, altrimenti aggiunge)
    if grep -q "^PORT=" "$ENV_DEST"; then
        sed -i 's/^PORT=.*/PORT=8002/' "$ENV_DEST"
    else
        echo "PORT=8002" >> "$ENV_DEST"
    fi
    chmod 600 "$ENV_DEST"
    log "Env copiato da $ENV_SOURCE → $ENV_DEST (PORT=8002)"
else
    log "ATTENZIONE: $ENV_SOURCE non trovato. Crea manualmente $ENV_DEST con PORT=8002."
fi

# ── 5. Installa systemd service ───────────────────────────────────────────────
log "Installo $SERVICE_NAME.service"
if [[ -f "$SERVICE_SRC" ]]; then
    cp "$SERVICE_SRC" "/etc/systemd/system/$SERVICE_NAME.service"
else
    log "ATTENZIONE: $SERVICE_SRC non trovato. Installazione service saltata."
fi
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
sleep 3
systemctl is-active "$SERVICE_NAME" && log "Servizio $SERVICE_NAME attivo ✅" || log "ERRORE: $SERVICE_NAME non attivo ❌"

# ── 6. Sudoers per deploy user ────────────────────────────────────────────────
SUDOERS_LINE="$DEPLOY_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart $SERVICE_NAME, /usr/bin/systemctl is-active $SERVICE_NAME, /bin/systemctl restart $SERVICE_NAME, /bin/systemctl is-active $SERVICE_NAME"
SUDOERS_FILE="/etc/sudoers.d/90-genesi-widget-core"
if [[ ! -f "$SUDOERS_FILE" ]]; then
    echo "$SUDOERS_LINE" > "$SUDOERS_FILE"
    chmod 440 "$SUDOERS_FILE"
    log "Sudoers aggiornato: $SUDOERS_FILE"
fi

log ""
log "=== SETUP COMPLETATO ==="
log "Istanza widget-core: http://127.0.0.1:8002"
log "Env:                 $ENV_DEST"
log "Service:             $SERVICE_NAME"
log ""
log "PASSO SUCCESSIVO: aggiorna /etc/widget-service.env"
log "  GENESI_URL=http://127.0.0.1:8002"
log "Poi: sudo systemctl restart genesi-widget"
