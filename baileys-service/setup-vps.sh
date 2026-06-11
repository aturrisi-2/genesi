#!/bin/bash
# Setup Genesi Baileys Service su VPS
# Eseguire come: bash setup-vps.sh

set -e

BAILEYS_DIR="/opt/genesi-baileys"
SERVICE_NAME="genesi-baileys"

echo "=== Setup Genesi Baileys Service ==="

# 1. Crea directory e copia file
mkdir -p "$BAILEYS_DIR"
cp -r /opt/genesi/baileys-service/. "$BAILEYS_DIR/"

# 2. Crea .env se non esiste
if [ ! -f "$BAILEYS_DIR/.env" ]; then
    cp "$BAILEYS_DIR/.env.example" "$BAILEYS_DIR/.env"
    echo ""
    echo "⚠️  Modifica $BAILEYS_DIR/.env con le credenziali corrette:"
    echo "   GENESI_GROUP_EMAIL=whatsapp_group@genesi.group"
    echo "   GENESI_GROUP_PASSWORD=<password>"
fi

# 3. Installa dipendenze
cd "$BAILEYS_DIR"
npm install --omit=dev

# 4. Crea systemd service
cat > /etc/systemd/system/$SERVICE_NAME.service << 'EOF'
[Unit]
Description=Genesi WhatsApp Groups Bridge (Baileys)
After=network.target genesi.service
Wants=genesi.service

[Service]
Type=simple
User=luca
WorkingDirectory=/opt/genesi-baileys
ExecStart=/usr/bin/node /opt/genesi-baileys/index.js
Restart=on-failure
RestartSec=10
StandardOutput=append:/opt/genesi-baileys/baileys.log
StandardError=append:/opt/genesi-baileys/baileys.log
EnvironmentFile=/opt/genesi-baileys/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME

echo ""
echo "=== Setup completato ==="
echo ""
echo "Prossimi passi:"
echo "1. Modifica /opt/genesi-baileys/.env con le credenziali account Genesi"
echo "2. Crea l'account su Genesi: POST /auth/register"
echo "3. Avvia il servizio: systemctl start $SERVICE_NAME"
echo "4. Scansiona il QR code: journalctl -u $SERVICE_NAME -f"
echo "   (oppure: tail -f /opt/genesi-baileys/baileys.log)"
