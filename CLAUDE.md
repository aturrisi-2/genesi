# CLAUDE.md — Genesi Project Conventions

Questo file viene letto automaticamente da Claude Code all'avvio di ogni sessione (desktop, mobile, web).
Leggi tutto prima di fare qualsiasi modifica al codice.

---

## Branch e Deploy

**Ramo di produzione: `gold-faro-stable`**

- Il branch `main` NON viene usato per il deploy. Non pushare su `main`.
- Tutto il lavoro di sviluppo va su `gold-faro-stable` (o su un feature branch da mergeare in `gold-faro-stable`).
- Ogni push su `gold-faro-stable` attiva automaticamente l'**Auto Deploy VPS** (GitHub Actions workflow `.github/workflows/deploy-vps.yml`).
- Se ti viene assegnato un branch designato (es. `claude/...`), sviluppa lì e chiedi conferma prima di pushare su gold.

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
- **SSH NON è accessibile** dal container remoto di Claude Code (network policy blocca la porta 22).
- Per verificare lo stato del deploy: usa il tool GitHub MCP `mcp__github__actions_list` / `mcp__github__actions_get` per controllare i run del workflow `deploy-vps.yml`.
- Per vedere i log del deploy: `mcp__github__get_job_logs`.

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
