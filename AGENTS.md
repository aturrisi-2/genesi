# AGENTS.md — Genesi Project Conventions

Questo file viene letto automaticamente da Codex all'avvio di ogni sessione (desktop, mobile, web).
Leggi tutto prima di fare qualsiasi modifica al codice.

---

## Branch e Deploy

**Ramo di produzione: `gold-faro-stable`**

- Il branch `main` NON viene usato per il deploy. Non pushare su `main`.
- Tutto il lavoro di sviluppo va su `gold-faro-stable` (o su un feature branch da mergeare in `gold-faro-stable`).
- Ogni push su `gold-faro-stable` attiva automaticamente l'**Auto Deploy VPS** (GitHub Actions workflow `.github/workflows/deploy-vps.yml`).
- Se ti viene assegnato un branch designato (es. `Codex/...`), sviluppa lì e chiedi conferma prima di pushare su gold.

**Prima di iniziare qualsiasi sessione di lavoro:**
```bash
git fetch origin gold-faro-stable
git checkout gold-faro-stable
git pull origin gold-faro-stable
```
Il container remoto può essere clonato da una base non aggiornata. Esegui sempre il pull prima di leggere o modificare codice.

---

## VPS e Deploy

- **VPS**: `87.106.30.193`, servizio `genesi`, porta `8000`, directory `/opt/genesi`
- **SSH NON è accessibile** dal container remoto di Codex (network policy blocca la porta 22).
- Per verificare lo stato del deploy: usa il tool GitHub MCP `mcp__github__actions_list` / `mcp__github__actions_get` per controllare i run del workflow `deploy-vps.yml`.
- Per vedere i log del deploy: `mcp__github__get_job_logs`.

### VPS e log live tramite terminale interno Codex

Quando l'utente apre una sessione SSH verso il VPS nel terminale interno
dell'app Codex, usare quel terminale come fonte primaria per osservare stato e
log runtime.

- L'utente esegue i comandi interattivi nel terminale interno, inclusi quelli
  che richiedono `sudo` o password.
- Codex NON deve chiedere, ricevere, salvare o riutilizzare password del VPS.
- Codex deve leggere il terminale interno con `codex_app.read_thread_terminal`
  e interpretare output/log da li.
- Per log live generali:
```bash
sudo journalctl -u genesi -f -o short-iso
```
- Per log live focalizzati sulle automazioni:
```bash
sudo journalctl -u genesi -f -o short-iso | grep -E 'AUTOMATION_SKIPPED|AUTOMATION|MOLTBOOK|FACEBOOK|IG_|BIRTHDAY|GROUP|REMINDER'
```
- Per ridurre rumore iCloud/acme:
```bash
sudo journalctl -u genesi -f -o short-iso | grep -Ev 'ICLOUD_EVENTS|acme-challenge'
```
- Se il terminale è dentro un pager (`systemctl status`, `less`, ecc.), prima
  far premere `q` all'utente.
- Per interrompere un live log, far usare `Ctrl+C`.

---

## Imperativo Zero Regressioni ("Vento in Poppa")

Prima di ogni push su `gold-faro-stable`:
1. Esegui la suite di test: `pytest tests/ -x -q 2>&1 | tail -30`
2. Controlla che non ci siano nuovi fallimenti rispetto alla baseline.
3. I seguenti test falliscono per ragioni pre-esistenti (non correlate alle tue modifiche) e possono essere ignorati:
   - `test_icloud_full`, `test_icloud_logic`
   - `test_face_extraction`
   - `test_neural_brain_integration`
   - `test_force_evolution`
   - `test_reminder_system`
   - `test_document_query`
   - `test_emoji_integration_fixes`
4. Non committare mai se stai introducendo nuovi fallimenti.

---

## Architettura Chiave

- **`core/proactor.py`**: Orchestratore centrale deterministico. Routing: Identity → Tool → Knowledge → Relational.
- **`core/simple_chat.py`**: Entry point principale per chat. Chiama `proactor.handle()`.
- **`core/message_pipeline.py`**: Pipeline memory platform-independent (WhatsApp, Telegram, web, ecc.).
- **`core/storage.py`**: Storage asincrono key-value. Le chiavi user-scoped usano il pattern `<prefix>:<user_id>` (es. `profile:user123`, `chat:user123`). Non usare mai il `message` come chiave.
- **`core/group_context.py`** / `strip_group_ctx()` in `simple_chat.py`: La sintassi `[GRUPPO FAMILIARE: ...]` / `[GRUPPO: ...]` inietta contesto di gruppo nel prompt relazionale. Il tono viene inferito dal nome del gruppo (es. `casa/turrisi/famiglia` → "familiare e affettuoso").
- **`core/meta_messaging_bot.py`** / **`api/meta_messaging.py`**: Facebook Messenger e Instagram DM via webhook Meta. Namespace utente isolati per piattaforma (`fb_<psid>`, `ig_<igsid>`) — nessuna contaminazione con WhatsApp/Telegram/web. Firma `X-Hub-Signature-256` obbligatoria se `META_APP_SECRET` è configurato. Env: `META_APP_SECRET`, `META_VERIFY_TOKEN`, `FB_PAGE_ACCESS_TOKEN`, `IG_ACCESS_TOKEN`. Test di sicurezza dedicati: `tests/test_meta_messaging_security.py`.

---

## Git Push

Se `git push` fallisce con "unexpected disconnect" o errori di rete:
```bash
# Retry con backoff esponenziale (2s, 4s, 8s, 16s)
# Oppure usa il tool MCP: mcp__github__push_files
```
Il tool `mcp__github__push_files` permette di pushare file singoli via GitHub API come fallback.

---

## Scope GitHub MCP

Il tool GitHub MCP è limitato al repository `aturrisi-2/genesi`. Non tentare di accedere ad altri repository senza prima chiamare `mcp__claude-code-remote__list_repos`.

---

## Credenziali e Sicurezza

- Non scrivere mai credenziali (password, token, chiavi SSH) nei file del repository o nei messaggi di commit.
- Se l'utente condivide credenziali in chat, avvisalo immediatamente di cambiarle e usare autenticazione a chiave SSH invece.

---

## Stato Lavori — Sessione 2026-06-15

### Completato ✅

**Migrazione Face Recognition: VGGFace2 → InsightFace ArcFace**
- `core/biometric_service.py` riscritto per usare InsightFace `buffalo_l` (RetinaFace + ArcFace 512-dim)
- Vecchi embedding VGGFace2 (`.pt`, `.npy`) rinominati automaticamente a `.bak_v1` al primo avvio
- Nuovo formato: numpy `.npy` `[N, 512]` L2-normalizzati (no torch dependency)
- Soglie tunabili via env senza redeploy: `FACE_MATCH_THRESHOLD` (default 0.6), `FACE_MATCH_MARGIN` (default 0.0), `FACE_MATCH_CONFIDENT_DIST` (default 0.3)
- `requirements.txt` aggiornato: `insightface>=1.0.0`, `onnxruntime>=1.18.0`, `opencv-python-headless>=4.8.0`
- Deploy VPS completato (run #910, `conclusion: success`), servizio `genesi` riavviato
- Verificato: riconoscimento funziona sul VPS (utente testato con foto + cane)

**Meta Messaging Webhook (Messenger + Instagram DM)**
- `core/meta_messaging_bot.py` + `api/meta_messaging.py` implementati
- Verifica HMAC-SHA256 (`X-Hub-Signature-256`) — 403 su token errato
- Test di sicurezza: `tests/test_meta_messaging_security.py` (50 test, tutti verdi)

### Da Fare / Pendente ⏳

**1. Meta Webhook — Variabili d'ambiente sul VPS**
Il codice è pronto ma il webhook non è attivo finché non si aggiungono questi 4 valori a `/opt/genesi/.env` sul VPS (via SSH dall'utente):
```
META_APP_SECRET=<da developers.facebook.com → Impostazioni app → Di base → App Secret>
META_VERIFY_TOKEN=<stringa libera che scegli tu, es. genesi_webhook_2024>
FB_PAGE_ACCESS_TOKEN=<da Messenger → Genera token, collegando la Pagina Facebook>
IG_ACCESS_TOKEN=<da Instagram → Genera token, collegando l'account IG Business>
```
Dopo aver aggiunto le variabili, riavviare il servizio: `sudo systemctl restart genesi`

Poi configurare su developers.facebook.com:
- Webhook URL: `https://<tuo-dominio>/api/messenger/webhook` e `/api/instagram/webhook`
- Verify Token: stesso valore di `META_VERIFY_TOKEN`
- Campi da sottoscrivere: `messages`, `messaging_postbacks`

**2. Test espressioni diverse — Face Recognition**
Verificare che il miglioramento ArcFace funzioni: inviare a Genesi una foto con espressione molto diversa rispetto a quella usata per la registrazione (es. registrato serio → test sorridente). Dovrebbe riconoscere correttamente dove prima falliva.

**3. Feature branch `Codex/genesis-activation-check-53nbre`**
Branch creato per il task di questa sessione. È allineato con `gold-faro-stable`. Non ci sono modifiche pendenti specifiche su questo branch — tutto è stato pushato direttamente su `gold-faro-stable`.

## Imported Claude Cowork project instructions
