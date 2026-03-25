# Genesi Widget — Guida completa

## Indice

1. [Cos'è il widget](#1-cosè-il-widget)
2. [Architettura del sistema](#2-architettura-del-sistema)
3. [Variabili d'ambiente necessarie](#3-variabili-dambiente-necessarie)
4. [Deploy sul VPS](#4-deploy-sul-vps)
5. [Come aggiungere una nuova chiave cliente](#5-come-aggiungere-una-nuova-chiave-cliente)
6. [Come configurare il widget dal pannello admin](#6-come-configurare-il-widget-dal-pannello-admin)
7. [Come integrare il widget nel sito del cliente](#7-come-integrare-il-widget-nel-sito-del-cliente)
8. [Intranet di test](#8-intranet-di-test)
9. [Tutti gli endpoint API](#9-tutti-gli-endpoint-api)
10. [Verifica funzionamento passo per passo](#10-verifica-funzionamento-passo-per-passo)
11. [Troubleshooting](#11-troubleshooting)
12. [Flusso completo di una conversazione](#12-flusso-completo-di-una-conversazione)

---

## 1. Cos'è il widget

Il widget è una finestra di chat embeddabile che il cliente incolla nel proprio sito/intranet con **una sola riga di codice**. Internamente si connette a Genesi AI e risponde in modo contestuale alla pagina aperta dall'utente.

**Caratteristiche principali:**

- Zero configurazione lato cliente (colore, nome, messaggio di benvenuto vengono dal server)
- Riconosce automaticamente i link presenti nella pagina e risponde con link pertinenti
- Cronologia persistente tra navigazioni (localStorage)
- Rate limiting per chiavi demo (max 20 messaggi/24h per IP)
- Supporto identità utente (nome e ruolo passati dalla piattaforma)
- Pronto per integrazione Google Workspace (scaffolding già presente)

---

## 2. Architettura del sistema

```
Browser cliente
    │
    │  <script src="widget.js" data-api-key="CHIAVE">
    │
    ▼
widget.js (frontend)
    │
    ├─► GET /api/widget/config          ← scarica nome, colore, welcome dal server
    │
    └─► POST /api/widget/chat           ← invia il messaggio dell'utente
            │
            ▼
        api/widget.py (FastAPI)
            │
            ├─ autentica con _get_token() → POST /auth/login (usa email+password della chiave)
            ├─ estrae link dalla pagina → _find_best_link() via LLM (gpt-4o-mini)
            ├─ scarica sottopagina se pertinente → _fetch_subpage_text()
            └─► POST /api/chat (Genesi core)
                    │
                    ▼
                risposta AI → tornata al browser
```

**File coinvolti:**

| File | Ruolo |
|------|-------|
| `api/widget.py` | Router FastAPI — autenticazione, rate limit, proxy verso Genesi core |
| `static/widget.js` | Script frontend embeddabile nel sito cliente |
| `static/admin-widget.html` | Pannello amministrazione widget |
| `static/intranet/` | Intranet di test (7 pagine) |
| `main.py` | Registra il router e le route `/intranet-test` |

---

## 3. Variabili d'ambiente necessarie

Aggiungere a `/opt/genesi/.env` sul VPS:

```env
# ── Widget — chiave singola ──────────────────────────────────────────────────
WIDGET_API_KEY=demo_cplace_2026
WIDGET_EMAIL=alfio.turrisi@gmail.com
WIDGET_PASSWORD=ZOEennio0810

# ── Widget — chiavi multiple (alternativo a singola) ─────────────────────────
# Formato: chiave1:email1:pass1,chiave2:email2:pass2
# WIDGET_KEYS=cliente_a:admin@clienteA.it:passA,cliente_b:admin@clienteB.it:passB

# ── Chiavi soggette a rate limit (demo, trial) ────────────────────────────────
WIDGET_RATE_LIMITED_KEYS=demo_cplace_2026

# ── Rate limiting: max messaggi per IP nella finestra temporale ───────────────
WIDGET_RATE_MAX=20
WIDGET_RATE_WINDOW=86400

# ── Token admin statico (alternativo al JWT di Genesi) ────────────────────────
WIDGET_ADMIN_TOKEN=scegli_un_token_segreto_lungo

# ── URL base di Genesi (usato internamente dal widget per il proxy) ───────────
BASE_URL=http://localhost:8000
```

Aggiungere le stesse a `/etc/genesi.env` (variabili systemd):

```bash
sudo nano /etc/genesi.env
# incollare le righe WIDGET_* e salvare
```

---

## 4. Deploy sul VPS

### 4a. Prima installazione

```bash
ssh luca@87.106.30.193
cd /opt/genesi
git pull origin gold-faro-stable

# Verifica variabili d'ambiente
grep WIDGET /opt/genesi/.env
grep WIDGET /etc/genesi.env

# Restart Genesi
sudo systemctl restart genesi
sudo systemctl status genesi   # deve mostrare "active (running)"

# Verifica che risponda
curl -s https://genesi.lucadigitale.eu/api/widget/ping \
  -H "X-Widget-Key: demo_cplace_2026"
# Risposta attesa: {"ok": true}
```

### 4b. Aggiornamento dopo nuovi commit

```bash
ssh luca@87.106.30.193
cd /opt/genesi
git pull origin gold-faro-stable
sudo systemctl restart genesi
```

---

## 5. Come aggiungere una nuova chiave cliente

### Metodo A — dal pannello admin (consigliato)

1. Aprire `https://genesi.lucadigitale.eu/admin-widget`
2. Fare login con le credenziali admin Genesi
3. Sezione **Gestione Chiavi API** → compilare il form:
   - **Label**: nome leggibile (es. "Cliente Rossi Srl")
   - **API Key**: identificativo univoco (es. `rossi_2026`)
   - **Email**: email dell'account Genesi dedicato al cliente
   - **Password**: password dell'account Genesi
   - **Rate limited**: spuntare solo per chiavi demo/trial
4. Cliccare **Crea Chiave**

> La chiave è attiva immediatamente senza restart.

### Metodo B — da variabili d'ambiente (persistente tra restart)

Aggiungere al file `/opt/genesi/.env`:

```env
WIDGET_KEYS=demo_cplace_2026:alfio@gmail.com:pass1,rossi_2026:admin@rossi.it:pass2
```

Poi:

```bash
sudo systemctl restart genesi
```

> Le chiavi create via pannello admin esistono solo in memoria. Se Genesi viene riavviato, sopravvivono solo quelle nell'env. Per produzione usare sempre il metodo B.

---

## 6. Come configurare il widget dal pannello admin

1. Aprire `https://genesi.lucadigitale.eu/admin-widget`
2. Sezione **Configura Widget** → selezionare la chiave dal menu
3. Compilare i campi:
   - **Nome assistente**: testo che compare nell'header del widget (es. "Assistente C-Place")
   - **Colore brand**: hex color (es. `#c41230`) — anteprima live nel quadratino
   - **Messaggio di benvenuto**: testo del primo messaggio (es. "Ciao! Come posso aiutarti?")
   - **Posizione**: bottom-right o bottom-left
   - **Placeholder**: testo dell'input (es. "Scrivi un messaggio...")
4. Cliccare **Salva configurazione**

La modifica è **immediata**: al prossimo caricamento della pagina del cliente il widget mostrerà i nuovi valori. Il cliente non deve toccare nulla.

---

## 7. Come integrare il widget nel sito del cliente

### Caso A — zero configurazione (raccomandato)

Il cliente incolla **solo questo** prima di `</body>`:

```html
<script
  src="https://genesi.lucadigitale.eu/widget.js"
  data-api-key="LA_CHIAVE_DEL_CLIENTE"
  data-page-context="true">
</script>
```

Nome, colore e messaggio di benvenuto vengono scaricati automaticamente dal server.

### Caso B — con identità utente (intranet con login)

Se la piattaforma conosce l'utente loggato, passare nome e ruolo:

```html
<script
  src="https://genesi.lucadigitale.eu/widget.js"
  data-api-key="LA_CHIAVE_DEL_CLIENTE"
  data-user-name="Mario Rossi"
  data-user-role="Amministrazione"
  data-page-context="true">
</script>
```

Il widget saluta l'utente per nome e il contesto viene passato a Genesi.

### Caso C — override locale della configurazione

Se si vuole forzare un colore o nome diverso da quello sul server:

```html
<script
  src="https://genesi.lucadigitale.eu/widget.js"
  data-api-key="LA_CHIAVE_DEL_CLIENTE"
  data-name="Help Desk"
  data-color="#e63946"
  data-welcome="Benvenuto! Sono qui per aiutarti."
  data-position="bottom-left"
  data-page-context="true">
</script>
```

Gli attributi `data-*` specificati nel tag HTML hanno sempre la precedenza sulla config server.

### Attributi disponibili

| Attributo | Obbligatorio | Default | Descrizione |
|-----------|-------------|---------|-------------|
| `data-api-key` | **SI** | — | Chiave univoca del cliente |
| `data-api-url` | No | stesso dominio | URL base di Genesi (es. `https://genesi.lucadigitale.eu`) |
| `data-name` | No | dal server | Nome dell'assistente |
| `data-color` | No | dal server | Colore brand (#hex) |
| `data-welcome` | No | dal server | Messaggio di benvenuto |
| `data-position` | No | dal server | `bottom-right` o `bottom-left` |
| `data-placeholder` | No | dal server | Placeholder dell'input |
| `data-page-context` | No | `true` | Invia il testo della pagina a Genesi |
| `data-user-name` | No | — | Nome dell'utente loggato |
| `data-user-role` | No | — | Ruolo/reparto dell'utente |
| `data-avatar` | No | — | URL immagine avatar assistente |

---

## 8. Intranet di test

L'intranet di test è un ambiente multi-pagina realistico per verificare il widget in condizioni reali.

**URL:** `https://genesi.lucadigitale.eu/intranet-test`

**Pagine disponibili:**

| Pagina | URL | Contenuto |
|--------|-----|-----------|
| Dashboard | `/intranet-test` | Home con 6 card di accesso + ultime news |
| Comunicazioni | `/intranet-test/comunicazioni.html` | 5 comunicati aziendali realistici |
| Welfare | `/intranet-test/welfare.html` | Convenzioni, buoni pasto, assicurazione |
| Salute & Sicurezza | `/intranet-test/salute.html` | Policy, registro infortuni, medico aziendale |
| Organigrammi | `/intranet-test/organigrammi.html` | Struttura per divisioni |
| Mensa | `/intranet-test/mensa.html` | Menu settimanale, orari, prenotazione |
| Rubrica | `/intranet-test/rubrica.html` | 15 contatti aziendali |

**Cosa testare navigando l'intranet:**

1. **Persistenza chat** — aprire il widget su una pagina, scrivere un messaggio, navigare su un'altra pagina → la conversazione deve essere ancora lì
2. **Contesto pagina** — chiedere "cosa c'è in questa pagina?" su pagine diverse → risposta contestuale
3. **Link automatici** — su mensa chiedere "dove si prenota il pasto?" → il widget deve rispondere con un link pertinente
4. **Identità utente** — il widget saluta "Alfio" e sa che è Direzione
5. **Config server** — il widget prende colore e nome dal server senza `data-color` o `data-name` nel tag

---

## 9. Tutti gli endpoint API

### Pubblici (richiedono solo X-Widget-Key)

```
GET  /api/widget/ping
     Header: X-Widget-Key: CHIAVE
     Risposta: {"ok": true}
     Uso: verifica che la chiave sia valida e il servizio attivo

GET  /api/widget/config
     Header: X-Widget-Key: CHIAVE
     Risposta: {"name": "...", "color": "#...", "welcome": "...", "position": "...", "placeholder": "..."}
     Uso: widget.js lo chiama all'avvio per auto-configurarsi

POST /api/widget/chat
     Header: X-Widget-Key: CHIAVE
     Body: {
       "message": "testo del messaggio",
       "page_url": "https://...",           (opzionale)
       "page_title": "Titolo pagina",       (opzionale)
       "page_context": "testo pagina...",   (opzionale)
       "conversation_id": "uuid",           (opzionale, per continuare conversazione)
       "user_name": "Mario Rossi",          (opzionale)
       "user_role": "Amministrazione"       (opzionale)
     }
     Risposta: {"response": "...", "conversation_id": "uuid"}
```

### Admin (richiedono X-Admin-Token OPPURE JWT Bearer admin)

```
GET    /api/widget/admin/keys
       Risposta: {"keys": [{key, label, email, calls, last_call, rate_limited}, ...]}

POST   /api/widget/admin/keys
       Body: {"key": "...", "email": "...", "password": "...", "label": "...", "rate_limited": false}
       Risposta: {"ok": true, "key": "..."}

DELETE /api/widget/admin/keys/{key}
       Risposta: {"ok": true, "revoked": "..."}

GET    /api/widget/admin/config/{key}
       Risposta: {"ok": true, "config": {name, color, welcome, position, placeholder, allowed_domains}}

PATCH  /api/widget/admin/config/{key}
       Body: {"name": "...", "color": "#...", "welcome": "...", "position": "...", "placeholder": "..."}
       Risposta: {"ok": true, "config": {...}}
```

**Come autenticarsi negli endpoint admin:**

```bash
# Metodo 1 — token statico
curl -H "X-Admin-Token: il_tuo_token" https://genesi.lucadigitale.eu/api/widget/admin/keys

# Metodo 2 — JWT Genesi (login prima)
TOKEN=$(curl -s -X POST https://genesi.lucadigitale.eu/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alfio.turrisi@gmail.com","password":"ZOEennio0810"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" https://genesi.lucadigitale.eu/api/widget/admin/keys
```

---

## 10. Verifica funzionamento passo per passo

### Step 1 — Ping base

```bash
curl -s https://genesi.lucadigitale.eu/api/widget/ping \
  -H "X-Widget-Key: demo_cplace_2026"
```
**Atteso:** `{"ok": true}`

**Se risponde 401:** la chiave non è caricata. Verificare env e riavviare Genesi.

---

### Step 2 — Config server

```bash
curl -s https://genesi.lucadigitale.eu/api/widget/config \
  -H "X-Widget-Key: demo_cplace_2026" | python3 -m json.tool
```
**Atteso:**
```json
{
  "name": "Assistente",
  "color": "#7c3aed",
  "welcome": "Ciao! Come posso aiutarti oggi?",
  "position": "bottom-right",
  "placeholder": "Scrivi un messaggio..."
}
```

---

### Step 3 — Chat base

```bash
curl -s -X POST https://genesi.lucadigitale.eu/api/widget/chat \
  -H "X-Widget-Key: demo_cplace_2026" \
  -H "Content-Type: application/json" \
  -d '{"message": "ciao"}' | python3 -m json.tool
```
**Atteso:** `{"response": "Ciao! ...", "conversation_id": "uuid-..."}`

**Se risponde 503:** Genesi core non è raggiungibile. Verificare `sudo systemctl status genesi`.

---

### Step 4 — Lista chiavi admin

```bash
TOKEN=$(curl -s -X POST https://genesi.lucadigitale.eu/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alfio.turrisi@gmail.com","password":"ZOEennio0810"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s https://genesi.lucadigitale.eu/api/widget/admin/keys \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```
**Atteso:** array con almeno la chiave `demo_cplace_2026`.

---

### Step 5 — Modifica config via API

```bash
curl -s -X PATCH \
  https://genesi.lucadigitale.eu/api/widget/admin/config/demo_cplace_2026 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Assistente Intranet", "color": "#1a56db"}' | python3 -m json.tool
```
**Atteso:** `{"ok": true, "config": {...}}`

Dopo questo, ricaricare l'intranet di test: il widget deve mostrare il nuovo nome e colore.

---

### Step 6 — Intranet di test nel browser

1. Aprire `https://genesi.lucadigitale.eu/intranet-test`
2. Cliccare il pulsante viola in basso a destra
3. Scrivere "ciao" → risposta naturale (non elenco di link)
4. Scrivere "cosa c'è nella pagina?" → risposta contestuale al contenuto
5. Navigare su **Mensa** → scrivere "a che ora è aperta?" → risposta con orari dalla pagina
6. Tornare su **Dashboard** → la cronologia deve essere ancora presente
7. Aggiornare la pagina → la cronologia deve persistere (localStorage)

---

## 11. Troubleshooting

### Il widget non appare

- Aprire la console del browser (F12) → cercare `[GenesiWidget]`
- Se compare `data-api-key mancante`: il tag script non ha l'attributo `data-api-key`
- Se compare un errore di rete: verificare che l'URL del server sia corretto e raggiungibile

### Il widget risponde 401

```bash
# Verificare che la chiave sia caricata
curl -s https://genesi.lucadigitale.eu/api/widget/ping \
  -H "X-Widget-Key: demo_cplace_2026"
```

Se risponde `{"detail": "API key non valida"}`:
```bash
ssh luca@87.106.30.193
grep WIDGET /opt/genesi/.env          # verifica che le variabili ci siano
grep WIDGET /etc/genesi.env           # verifica il file systemd
sudo systemctl restart genesi
```

### Il widget risponde 503

Genesi core non è raggiungibile internamente:
```bash
ssh luca@87.106.30.193
sudo systemctl status genesi
sudo journalctl -u genesi -n 50       # ultimi 50 log
```

### La config visuale non viene applicata

Il widget carica la config dal server via `GET /api/widget/config`. Se la risposta non cambia dopo un PATCH:
- La config è in memoria — se Genesi è stato riavviato dopo il PATCH, i valori sono tornati ai default
- Soluzione definitiva: le config visuali devono essere salvate su file JSON o database (miglioramento futuro)

### Il pannello admin mostra 0 chiavi

```bash
ssh luca@87.106.30.193
# Verifica variabili nel processo in esecuzione
pid=$(systemctl show genesi --property=MainPID --value)
strings /proc/$pid/environ | grep WIDGET
```

Se non compaiono: le variabili non sono state rilette dopo il restart. Verificare `/etc/genesi.env` e riavviare.

### La chat si resetta tra le pagine

Il localStorage è diviso per origine (dominio+porta). Se l'intranet è su un dominio diverso da Genesi, il widget usa `data-api-url` e le chiavi localStorage sono corrette. Verificare in console:
```javascript
Object.keys(localStorage).filter(k => k.startsWith('gw_'))
```

Deve esserci almeno `gw_conv_...` e `gw_msgs_...`.

### Rate limit raggiunto

La chiave demo è limitata a 20 messaggi ogni 24 ore per IP. Il contatore è in memoria e si resetta al restart di Genesi. Per test intensivi usare una chiave non rate-limited o modificare `WIDGET_RATE_MAX=9999` nell'env.

---

## 12. Flusso completo di una conversazione

```
1. Il browser carica la pagina del cliente
   └─► esegue widget.js

2. widget.js legge data-api-key dal tag <script>

3. widget.js chiama GET /api/widget/config (X-Widget-Key: CHIAVE)
   └─► server ritorna {name, color, welcome, position, placeholder}
   └─► widget.js applica i valori e costruisce la UI

4. L'utente clicca il pulsante del widget
   └─► se ci sono messaggi in localStorage → li ripristina
   └─► altrimenti mostra il messaggio di benvenuto

5. L'utente scrive un messaggio e preme invio

6. widget.js raccoglie il contesto della pagina corrente:
   - testo visibile (max 2000 char)
   - tutti i link con testo e URL

7. widget.js chiama POST /api/widget/chat con:
   - message, page_url, page_title, page_context, conversation_id, user_name, user_role

8. api/widget.py riceve la richiesta:
   a. verifica la chiave in _WIDGET_CONFIGS
   b. controlla rate limit (se chiave demo)
   c. ottiene il JWT Genesi con _get_token() (cached 30 giorni)
   d. estrae i link dalla page_context → link_map
   e. chiama _find_best_link() via LLM → trova il link più pertinente (o None)
   f. se trovato: scarica il contenuto della sottopagina con _fetch_subpage_text()
   g. costruisce il messaggio finale con contesto + istruzione comportamentale
   h. chiama POST /api/chat di Genesi core
   i. post-processa la risposta (inietta link mancanti)
   j. aggiorna usage stats
   k. ritorna {"response": "...", "conversation_id": "..."}

9. widget.js mostra la risposta nel pannello
   └─► salva il messaggio in localStorage
   └─► aggiorna conversation_id per il prossimo turno

10. L'utente naviga su un'altra pagina
    └─► widget.js su nuova pagina legge localStorage
    └─► al click sul widget ripristina la cronologia (senza ri-chiamare il server)
```

---

*Documento generato il 25 marzo 2026 — versione attuale: commit `01eda17` su branch `gold-faro-stable`*
