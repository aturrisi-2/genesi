# Auto Deploy VPS (gold-faro-stable)

Questo setup esegue il deploy automatico su VPS ad ogni push su `gold-faro-stable`.

## 1) Prerequisiti VPS

Esegui sul VPS (una sola volta):

```bash
sudo useradd -m -s /bin/bash deploy || true
sudo mkdir -p /opt/genesi
sudo chown -R deploy:deploy /opt/genesi
```

Clona la repo come utente deploy:

```bash
sudo -u deploy -H bash -lc 'cd /opt && git clone https://github.com/aturrisi-2/genesi.git'
sudo -u deploy -H bash -lc 'cd /opt/genesi && git checkout gold-faro-stable'
```

Permetti restart del servizio senza password (sudoers):

```bash
echo 'deploy ALL=(root) NOPASSWD: /bin/systemctl restart genesi, /bin/systemctl restart genesi.service, /bin/systemctl is-active genesi, /bin/systemctl is-active genesi.service, /usr/bin/systemctl restart genesi, /usr/bin/systemctl restart genesi.service, /usr/bin/systemctl is-active genesi, /usr/bin/systemctl is-active genesi.service' | sudo tee /etc/sudoers.d/genesi-deploy
sudo chmod 440 /etc/sudoers.d/genesi-deploy
sudo visudo -cf /etc/sudoers.d/genesi-deploy
```

## 2) Chiave SSH per GitHub Actions

Genera una chiave dedicata (sul tuo PC locale):

```bash
ssh-keygen -t ed25519 -f ./genesi_deploy_key -C "github-actions-deploy"
```

Aggiungi la chiave pubblica sul VPS in `~deploy/.ssh/authorized_keys`.

## 3) Secrets su GitHub

In `Settings > Secrets and variables > Actions`, crea:

- `VPS_HOST` = IP o dominio del VPS
- `VPS_PORT` = porta SSH (es. `22`)
- `VPS_USER` = `deploy` (o il tuo utente)
- `VPS_SSH_KEY` = contenuto **privato** di `genesi_deploy_key`

## 4) Workflow già incluso nella repo

File: `.github/workflows/deploy-vps.yml`

Trigger:
- push su `gold-faro-stable`
- esecuzione manuale (`workflow_dispatch`)

## 5) Verifica deploy

Dopo un push su `gold-faro-stable`, controlla i log workflow su GitHub e poi sul VPS:

```bash
sudo journalctl -u genesi -n 100 -o cat
```

## Note

- Lo script di deploy usato dal workflow è: `scripts/vps_autodeploy.sh`.
- Il deploy è in modalità receiver puro: ad ogni run fa `git fetch`, `git reset --hard origin/gold-faro-stable` e `git clean -fd`.
- Il VPS non deve mantenere modifiche locali: eventuali file/patch locali vengono scartati automaticamente.
- Lo script installa dipendenze da `requirements.txt` dentro `/opt/genesi/.venv` (evita l'errore PEP 668 su Ubuntu 24+).
- Verifica che il servizio `genesi` usi il Python del virtualenv (es. `ExecStart=/opt/genesi/.venv/bin/python /opt/genesi/main.py`).
