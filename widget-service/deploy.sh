#!/bin/bash
# Deploy Genesi Widget Service su VPS
# Eseguire come: bash deploy.sh

set -e

DEPLOY_DIR="/home/luca/widget-service"
SERVICE_NAME="genesi-widget"

echo "==> Copia file..."
rsync -av --exclude='.env' --exclude='__pycache__' --exclude='*.pyc' \
  ./ luca@genesi.lucadigitale.eu:$DEPLOY_DIR/

echo "==> Installa dipendenze..."
ssh luca@genesi.lucadigitale.eu "cd $DEPLOY_DIR && pip install -r requirements.txt"

echo "==> Restart service..."
ssh luca@genesi.lucadigitale.eu "sudo systemctl restart $SERVICE_NAME"

echo "==> Status:"
ssh luca@genesi.lucadigitale.eu "sudo systemctl status $SERVICE_NAME --no-pager"

echo "✓ Deploy completato"
