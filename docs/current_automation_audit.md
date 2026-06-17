# Genesi — Audit Automazioni Proattive (FASE 0)

> Documento prodotto prima di qualsiasi disattivazione. Scopo: censire OGNI
> comportamento in cui Genesi avvia comunicazioni o pubblica contenuti **senza
> una richiesta esplicita dell'utente nello stesso istante**, e definire come
> spegnerlo in modo reversibile (feature flag, nessuna cancellazione di codice).
>
> Data audit: 2026-06-17 · Branch di lavoro: `genesi-operational-memory`
> Branch di produzione (protetto): `gold-faro-stable`

---

## 0. Sintesi esecutiva

Genesi oggi è **attiva e proattiva su 6 superfici outbound** e su 2 superfici
interne (training/health). Le automazioni proattive si dividono in:

- **Scheduler in background** avviati nel `lifespan` di `main.py` (10 task).
- **Reazioni autonome guidate da messaggi** nei bot di gruppo (interventi
  spontanei, auto-presentazione, saluti personalizzati).
- **Risposte automatiche a commenti** su Instagram / Facebook / Moltbook.

**NON esiste oggi un interruttore centralizzato.** I controlli sono sparsi e
incoerenti: `IG_PUBLISHER_ENABLED` (env), `MOLTBOOK_API_KEY` presente/assente,
`facebook:config.enabled` (storage), nessun gate per saluti e compleanni.

La FASE 0 introduce un modulo unico `core/automation_flags.py` con un
**master switch `GENESI_PASSIVE_MODE` (default `true`)** che forza OFF ogni
automazione proattiva, più flag granulari (default OFF). Le funzioni di
risposta su richiesta (chat web, WhatsApp/Telegram 1:1, foto, vocali, manuali
medici) **restano intatte**. I reminder automatici sono trattati come attività
proattiva e restano OFF di default, riattivabili solo esplicitamente.

---

## 1. Inventario automazioni individuate

Legenda Stato post-modifica: **OFF** = disattivata da flag (default passivo) ·
**ON-on-request** = resta attiva solo se interpellata · **OFF (interno)** =
processo interno non-outbound, disattivato per prudenza/costi.

### 1.1 Scheduler in background (`main.py` → `lifespan`)

| # | Task | File / funzione | Trigger / Frequenza | Cosa fa (impatto) | Stato post-modifica | Flag |
|---|------|-----------------|---------------------|-------------------|---------------------|------|
| 1 | Reminder checker | `main.py:reminder_checker_background` | loop ogni **30s** | Consegna in chat + **email** i reminder scaduti impostati dall'utente | **OFF** per default in passive mode; riattivabile esplicitamente | `ENABLE_REMINDERS`, `ENABLE_PROACTIVE_EMAIL` |
| 2 | Calendar checker | `main.py:calendar_checker_background` | loop ogni **5 min** | Logga eventi imminenti (oggi **solo log**, nessun outbound) | ON (innocuo) | `ENABLE_CALENDAR_CHECK` |
| 3 | Lab cycle scheduler | `main.py:lab_cycle_scheduler` | — | **GIÀ DISABILITATO** in codice (`DISABLED TO PREVENT CREDIT DRAIN`) | OFF (già) | — |
| 4 | Evolution scheduler | `main.py:evolution_scheduler` | — | **GIÀ DISABILITATO** in codice | OFF (già) | — |
| 5 | Training autopilot | `core/training_autopilot.py:run_background_loop` | loop ogni **1h** | Snapshot, rotazione lessons, training automatico (consumo crediti LLM) | **OFF (interno)** | `ENABLE_TRAINING_AUTOPILOT` |
| 6 | **Moltbook heartbeat** | `main.py:moltbook_heartbeat_background` → `core/moltbook_service.py:heartbeat` | loop ogni **4h** | **Pubblica post autonomi**, commenta, **segue/non-segue agenti**, upvota, segnala spam su `moltbook.com` | **OFF** | `ENABLE_MOLTBOOK_AUTOPUBLISH` |
| 7 | Improvement health | `core/improvement_health.py:run_background_loop` | loop | Monitoraggio interno qualità | OFF (interno) | `ENABLE_IMPROVEMENT_HEALTH` |
| 8 | **Facebook heartbeat** | `main.py:facebook_heartbeat_background` → `core/facebook_service.py:heartbeat` | loop ogni **2–4h** (jitter) | Browser Playwright: **crea post nei gruppi FB**, commenta, risponde a commenti, mette like (persona "Giada") | **OFF** | `ENABLE_FACEBOOK_AUTOMATION` |
| 9 | **Birthday / saluti mattutini** | `core/birthday_service.py:birthday_scheduler` | loop 30s, **spara alle 6:30 / 6:45 / 8:45** | **Saluti proattivi mattutini** a TUTTI i gruppi Telegram + WhatsApp noti, auguri compleanno, **immagine generata** per il gruppo configurato | **OFF** | `ENABLE_MORNING_GREETINGS`, `ENABLE_BIRTHDAY_GREETINGS` |
| 10 | **Instagram publisher** | `main.py` → `core/instagram_publisher.py:instagram_publisher_scheduler` | loop 5 min, **post alle 10:30 / 17:30**, reel ogni 3 gg | **Pubblica post e Reel autonomi** su `@genesiai_official`, **risponde ai commenti** (polling) | **OFF** | `ENABLE_INSTAGRAM_POSTING`, `ENABLE_INSTAGRAM_REELS`, `ENABLE_INSTAGRAM_COMMENT_REPLIES` |

> Nota: l'Instagram publisher è **già** gated da `IG_PUBLISHER_ENABLED` (default
> off). La FASE 0 lo subordina anche al master switch e ai flag granulari.

### 1.2 Reazioni autonome guidate da messaggi (bot di gruppo)

| # | Automazione | File / funzione | Trigger | Cosa fa | Stato post-modifica | Flag |
|---|-------------|-----------------|---------|---------|---------------------|------|
| 11 | **Intervento spontaneo in gruppo** | `core/whatsapp_bot.py` / `core/telegram_bot.py` → `_group_should_intervene` | ad ogni messaggio di gruppo | Genesi **decide da sola** se intromettersi in una conversazione di gruppo non indirizzata a lei | **OFF** | `ENABLE_GROUP_INTERVENTIONS` |
| 12 | **Auto-presentazione in gruppo** | `core/group_presentation.py:maybe_present_in_group` | primo contatto con un gruppo nuovo | Manda spontaneamente un messaggio di presentazione quando viene aggiunta a un gruppo | **OFF** | `ENABLE_GROUP_AUTO_PRESENTATION` |
| 13 | **Saluto personalizzato di gruppo** | `core/group_greeting_service.py:build_personalized_greeting`, `_welcome_new_member` Telegram | quando un membro saluta o entra in un gruppo familiare | Risponde con saluto + meteo + battute, o benvenuto automatico a nuovo membro | **OFF** | `ENABLE_GROUP_GREETING_REPLIES` |
| 14 | **Campagna DM compleanni** | `core/birthday_service.py:collect_birthday_dm` (+ invii `_send_wa_*`) | scheduler / DM | Invia DM per raccogliere date di nascita e poi auguri | **OFF** | `ENABLE_BIRTHDAY_GREETINGS` |

> `extract_and_save_member_info` (estrazione passiva nome/città dai messaggi) e
> `try_extract_birthday` **non sono outbound**: salvano dati, non scrivono a
> nessuno. Restano attivi (nessuna comunicazione proattiva).

### 1.3 Risposte automatiche a contenuti esterni

| # | Automazione | File / funzione | Trigger | Stato post-modifica | Flag |
|---|-------------|-----------------|---------|---------------------|------|
| 15 | Risposta commenti IG/Messenger | `core/instagram_publisher.py:poll_and_reply_comments`, `core/meta_messaging_bot.py:reply_to_comment` | polling 5 min + webhook | **OFF** | `ENABLE_INSTAGRAM_COMMENT_REPLIES` |
| 16 | Risposta commenti Facebook | `core/facebook_service.py:reply_to_comments_on_own_posts` | dentro heartbeat FB | **OFF** (con #8) | `ENABLE_FACEBOOK_AUTOMATION` |
| 17 | Risposta DM Messenger/IG (1:1) | `api/meta_messaging.py` (webhook) | messaggio in arrivo | **ON-on-request** (è una risposta a chi scrive) | `ENABLE_META_DM_REPLIES` (default ON) |

### 1.4 Altro

| # | Voce | Note |
|---|------|------|
| 18 | `set_webhook` Telegram allo startup | Registra il webhook (necessario per ricevere messaggi 1:1). Resta. |
| 19 | `notification_email.send_reminder_email` | Email proattiva per reminder. Gated da `ENABLE_PROACTIVE_EMAIL`. |

---

## 2. MOLTBOK / MULTBOOK / MOLTBOOK — chiarimento

Il sistema citato nel brief come "MOLTBOK / MULTBOOK" corrisponde a
**Moltbook** (`moltbook.com`), il social network per agenti AI integrato in
`core/moltbook_service.py` + `api/admin/moltbook.py`. È l'unico sistema di
pubblicazione autonoma su piattaforma esterna con quel nome.

- Pubblica post autonomi (`post_from_insights`, `post_memory_showcase`).
- Commenta, segue/non-segue, upvota, segnala spam.
- Entry point: `moltbook_service.heartbeat()` ogni 4h.

**Disattivazione**: il flag `ENABLE_MOLTBOOK_AUTOPUBLISH` (default OFF) — con
alias accettati `ENABLE_MOLTBOK_AUTOPUBLISH` e `ENABLE_MULTBOOK_AUTOPUBLISH`
per coprire entrambe le grafie del brief — blocca l'intero heartbeat.

---

## 3. Sistema centralizzato di disattivazione

Nuovo modulo: **`core/automation_flags.py`**.

### 3.1 Principi
1. **Master switch** `GENESI_PASSIVE_MODE` (default `true`): se attivo, ogni
   automazione proattiva è OFF a prescindere dai flag granulari.
2. **Default fail-safe**: ogni flag proattivo è OFF di default. Per riattivare
   serve un'azione esplicita (env var = `true`) **e** `GENESI_PASSIVE_MODE=false`.
3. **Nessuna cancellazione**: il codice resta; viene solo bypassato il punto di
   uscita outbound. Riattivabile senza redeploy (variabili ambiente).
4. **On-request intatto**: le risposte a chi interpella Genesi non passano dai
   flag proattivi.
5. **Controllo admin**: il pannello `/admin` espone una sezione "Automazioni"
   che salva override persistenti in `memory/admin/automation_flags.json`.
   Gli override admin hanno precedenza sulle variabili ambiente.

### 3.2 Variabili ambiente introdotte (tutte default sicuro)

```
# Master
GENESI_PASSIVE_MODE=true            # true = tutte le automazioni proattive OFF

# Saluti / messaggi proattivi
ENABLE_MORNING_GREETINGS=false
ENABLE_BIRTHDAY_GREETINGS=false
ENABLE_PROACTIVE_MESSAGES=false     # umbrella messaggi non sollecitati
ENABLE_GROUP_INTERVENTIONS=false
ENABLE_GROUP_AUTO_PRESENTATION=false
ENABLE_GROUP_GREETING_REPLIES=false

# Social / pubblicazione esterna
ENABLE_SOCIAL_AUTOPUBLISH=false     # umbrella social
ENABLE_INSTAGRAM_POSTING=false
ENABLE_INSTAGRAM_REELS=false
ENABLE_INSTAGRAM_COMMENT_REPLIES=false
ENABLE_FACEBOOK_AUTOMATION=false
ENABLE_MOLTBOOK_AUTOPUBLISH=false   # alias: ENABLE_MOLTBOK_/ENABLE_MULTBOOK_

# Interni
ENABLE_TRAINING_AUTOPILOT=false
ENABLE_IMPROVEMENT_HEALTH=false

# Restano abilitati (funzioni su richiesta / utili)
ENABLE_REMINDERS=false              # reminder automatici OFF in passive mode
ENABLE_PROACTIVE_EMAIL=false        # email reminder (proattiva → default OFF)
ENABLE_CALENDAR_CHECK=true          # solo log, nessun outbound
ENABLE_META_DM_REPLIES=true         # risposta a chi scrive in DM
```

---

## 4. Conferma esplicita stato target (post wiring)

Con `GENESI_PASSIVE_MODE=true` (default) e i flag ai default sopra:

- ✅ **Saluti automatici (mattutini/serali/compleanni) DISATTIVATI** — task #9, #14
- ✅ **Pubblicazioni Instagram (post + reel) DISATTIVATE** — task #10, #15
- ✅ **Pubblicazioni MOLTBOK / MULTBOOK / Moltbook DISATTIVATE** — task #6
- ✅ **Automazione Facebook DISATTIVATA** — task #8, #16
- ✅ **Interventi spontanei nei gruppi DISATTIVATI** — task #11, #12, #13
- ✅ **Comunicazioni proattive / messaggi non sollecitati DISATTIVATI**
- ✅ **Training autopilot interno DISATTIVATO** — task #5
- 🟢 **Genesi continua a rispondere quando interpellata** (chat web, DM
  WhatsApp/Telegram/Meta 1:1, foto, vocali, manuali).

> **Stato attuale del wiring**: i gate sono integrati nei punti di uscita
> outbound censiti e sono governati da `core/automation_flags.py`. Il deploy su
> `gold-faro-stable` rende effettiva la modalità passiva sul VPS.

---

## 5. Punti di iniezione del gate (piano FASE 0.b)

| Flag | File:funzione | Punto di gate |
|------|---------------|---------------|
| `morning_greetings` / `birthday_greetings` | `core/birthday_service.py:birthday_scheduler` | early-return all'inizio del loop / prima dell'invio |
| `moltbook_autopublish` | `core/moltbook_service.py:heartbeat` | early-return in cima |
| `facebook_automation` | `main.py:facebook_heartbeat_background` | skip chiamata `heartbeat()` |
| `instagram_*` | `core/instagram_publisher.py:instagram_publisher_scheduler` | gate per slot post/reel/commenti |
| `group_interventions` | `*_bot.py:_group_should_intervene` | ritorna "non intervenire" |
| `group_auto_presentation` | `core/group_presentation.py:maybe_present_in_group` | early-return `None` |
| `group_greeting_replies` | bot → `build_personalized_greeting` | skip invio saluto |
| `training_autopilot` | `core/training_autopilot.py:run_background_loop` | early-return |
| `proactive_email` | `main.py` reminder email branch | skip `send_reminder_email` |

Ogni gate logga `AUTOMATION_SKIPPED flag=<nome>` per osservabilità.
