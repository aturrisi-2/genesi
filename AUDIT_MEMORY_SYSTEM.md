# AUDIT — Sistema di Memoria Genesi
> Sessione: 2026-03-02 | Branch: gold-faro-stable
> Per: Genesi Pro (il prossimo agente che lavorerà su questo codebase)

---

## 1. OBIETTIVO DELL'UTENTE

Alfio (utente reale, user_id: `6028d92a-...`) vuole che Genesi si comporti come un **amico/assistente che ricorda davvero**: non solo nome e città, ma tutto ciò che gli è stato detto nel tempo — preferenze specifiche, informazioni sui familiari, abitudini, esperienze. La stessa fluidità di memoria che ha un buon amico.

**Comportamento desiderato (esempi reali dai log):**
- "zoe è stata a cork in irlanda" → sessione dopo → "dove è stata mia figlia?" → **risponde Cork** ✅
- "i miei piloti F1 sono Leclerc e Hamilton, tifo Ferrari" → "chi tifo?" → **risponde Ferrari** ✅
- "di solito ceno alle 20:30" → settimane dopo → Genesi lo ricorda e lo usa ✅
- "il mio cane si chiama Rio" → non cancella i gatti Mignolo e Prof ✅
- "non sono persiani, sono europei" → non salva "persiani" come professione ✅

---

## 2. ARCHITETTURA MEMORIA (4 LAYER)

```
LAYER 1: Profile strutturato (memory/profile/{user_id}.json)
  → name, city, profession, spouse, children[], pets[], interests[], preferences[], traits[]
  → Modificato da: cognitive_memory_engine (regex) + identity_extractor (LLM) + memory_correction (LLM)
  → Letto da: identity route, context_assembler

LAYER 2: Personal Facts (memory/personal_facts/{user_id}.json) ← NUOVO
  → Fatti conversazionali duraturi: dove è stata Zoe, piloti F1, abitudini, hobby specifici
  → Modificato da: personal_facts_service (background LLM, ogni turn)
  → Letto da: context_assembler (tutti i route) + _handle_identity (identity route)

LAYER 3: Episode Memory (memory/episodes/{user_id}.json)
  → Eventi temporali: appuntamenti, esperienze con data, follow-up futuro
  → Modificato da: episode_extractor (background LLM, ogni turn)
  → Letto da: context_assembler (tutti i route)
  → Scade: 30 giorni, max 50 episodi

LAYER 4: Global Insights (memory/global_insights/{user_id}.json)
  → Pattern comportamentali astratti: "preferisce risposte concise", "lavora di sera"
  → Modificato da: global_memory_service (ogni 1h se vuoto, 24h se già popolato)
  → Letto da: context_assembler (tutti i route)
```

**Regola d'oro dei layer**: dati strutturati → profile | fatti conversazionali → personal_facts | eventi con data → episodes | pattern astratti → global_insights

---

## 3. FILE MODIFICATI IN QUESTA SESSIONE

### 3.1 CREATO: `core/personal_facts_service.py`
**Cosa fa**: estrae e persiste fatti personali dalla conversazione (entrambi user+assistant message) in background.
**Componenti chiave**:
- `extract_and_save(user_message, assistant_response, user_id)` — entry point background
- `_extract()` — LLM gpt-4o-mini con `_call_model` (NON `_call_with_protection`!)
- `_save_facts()` — salva con deduplicazione per key + rilevamento conflitti semantici
- `_find_semantic_conflict()` — heuristica: ≥2 parole significative in comune + stessa categoria → sostituisce invece di aggiungere
- `get_relevant(user_id, query, limit)` — scoring per keyword overlap
- Max 100 fatti, FIFO, nessuna scadenza

**⚠️ ATTENZIONE**: il background task viene aggiunto in `api/chat.py` DOPO `simple_chat_handler` (ha bisogno della risposta del assistant). Diverso da episode/identity extractor che vanno PRIMA.

### 3.2 MODIFICATO: `api/chat.py`
Aggiunto background task `_extract_and_save_personal_facts()` in:
- Regular endpoint: dopo `response = await simple_chat_handler(...)` (line ~205)
- Streaming endpoint: dentro `_run_pipeline()` dopo `resp = await _sch(...)` (line ~300)

### 3.3 MODIFICATO: `core/context_assembler.py`
Aggiunta sezione `[FATTI PERSONALI APPRESI]` nel summary, dopo episodi e global insights (line ~171). Fail-silent. Usa `get_relevant(user_id, user_message, limit=8)`.

### 3.4 MODIFICATO: `core/proactor.py` — `_handle_identity`
- Carica `personal_facts_list = await _pfs.get_relevant(user_id, message, limit=10)` prima di costruire il system prompt
- Passa `personal_facts_list` a `_build_identity_system_prompt(facts, personal_facts_list)`

### 3.5 MODIFICATO: `core/proactor.py` — `_build_identity_system_prompt`
Aggiunta sezione "Fatti appresi dalla conversazione:" nel system prompt LLM quando personal_facts_list non è vuota.

### 3.6 MODIFICATO: `core/proactor.py` — `_handle_memory_correction`
**BUG CRITICO FIXATO**: usava `_call_with_protection` che sovrascriveva il `parse_prompt` con il sistema adattivo → il LLM non seguiva le istruzioni sul JSON → pets cancellate, campi sbagliati.
**Fix**: `_call_with_protection` → `_call_model` (stesso fix già fatto per _handle_memory_context, _synthesize_responses, global_memory_service)
**Merge safety aggiunta**: se pets/children update ha no overlap con esistenti → merge invece di replace
**Prompt migliorato**: istruzione esplicita di includere tutti gli animali esistenti nel new_value
**Fallback migliorato**: "Non ho capito" → "Capito, me lo segno!"
**Nuovo esempio**: "La mia auto è una Ford Focus" → salva in interests

### 3.7 MODIFICATO: `core/cognitive_memory_engine.py`
**Profession false positives fixati**:
1. Guard nomi propri multipli ("Leclerc e Hamilton" → skip)
2. Guard negazione: "non sono X" → controlla se testo prima del match finisce con "non" → skip
3. Aggiunto "nato/nata" agli stopwords ("sono nato a..." ≠ professione)
4. Aggiunto "razza" agli stopwords ("sono di razza X" ≠ professione)

---

## 4. PATTERN CRITICI DA NON ROMPERE MAI

### ❌ REGOLA #1: `_call_with_protection` vs `_call_model`
`_call_with_protection` SOVRASCRIVE il system prompt con il prompt adattivo da `lab/global_prompt.json`.
**Usare SEMPRE `_call_model` per chiamate interne con prompt specializzato**:
```
✅ _handle_memory_context
✅ _synthesize_responses
✅ global_memory_service._do_consolidate
✅ _handle_memory_correction (fixato in questa sessione)
✅ personal_facts_service._extract
✅ episode_extractor.extract_episodes
```
Se aggiungi un nuovo handler con un prompt JSON strutturato → usa `_call_model`.

### ❌ REGOLA #2: Background tasks sempre fail-silent
Tutti i background task di estrazione memoria devono essere avvolti in try/except e non devono mai interrompere il flusso chat. Usare `asyncio.create_task()` non `await`.

### ❌ REGOLA #3: Personal facts task DOPO simple_chat_handler
Il personal_facts extractor ha bisogno della risposta dell'assistant. Va aggiunto DOPO `simple_chat_handler`, non prima come episode/identity extractor.

### ❌ REGOLA #4: Storage keys consistenti
```
profile:{user_id}          → memory/profile/{user_id}.json
episodes:{user_id}         → memory/episodes/{user_id}.json
personal_facts:{user_id}   → memory/personal_facts/{user_id}.json
global_insights:{user_id}  → memory/global_insights/{user_id}.json
relational_state:{user_id} → memory/relational_state/{user_id}.json
```

### ❌ REGOLA #5: chat_memory keys
`chat_memory.get_messages()` ritorna `{"user_message": ..., "system_response": ...}` — NON `role/content`

---

## 5. BUG NOTI / WORKAROUND ESISTENTI

### 5.1 Profession field nel profilo Alfio è corrotta
Il profilo reale su Ubuntu ha `'profession': 'persiani'` (leftover dai test). Il guard in `_handle_identity` la pulirà automaticamente perché "persiani" è ora in `_PROFESSION_STOPWORDS`. Ma se non viene pulita, Alfio deve dire "faccio il [lavoro reale]" per correggerla.

### 5.2 Pets nel profilo Alfio sono incomplete
Il profilo ha solo `[Rio]` invece di `[Mignolo, Prof, Rio]`. Per ripristinare: Alfio deve dire "ho due gatti, Mignolo e Prof, e un cane Rio". Con il merge fix, ora aggiungerà i gatti senza cancellare Rio.

### 5.3 City nel profilo Alfio oscilla Roma/Imola
La city "Imola" è stata corretta in sessione tramite memory_correction ma il profilo base su disco ancora dice "Roma". Alfio deve ridire "vivo a Imola" per fixarlo definitivamente.

### 5.4 `_find_semantic_conflict` con threshold 40%
Il threshold del 40% è conservativo. Potrebbe non catturare tutti i conflitti (es. due fatti con 1 sola parola in comune) ma evita falsi positivi. Se si osservano fatti duplicati simili, abbassare a 30%.

### 5.5 `get_relevant` ritorna tutti i fatti quando nessun match
Se la query non ha match diretti, `get_relevant` restituisce gli 8 più recenti. Questo significa che il context assembler può iniettare fatti non rilevanti. Considera di aggiungere un threshold minimo (score > 0) anche per il fallback.

---

## 6. COSA NON È STATO FATTO (TODO FUTURI)

### 6.1 Cognizione del tempo nelle conversazioni passate
L'utente vuole che Genesi "ricordi di cosa abbiamo parlato". Attualmente:
- `memory_context` route usa `chat_memory` (in-memory, perde al restart)
- `global_memory_service` estrae pattern ma non ricordi specifici
- `episodes` cattura eventi temporali ma non "di cosa abbiamo parlato"

**Soluzione suggerita**: aggiungere al `personal_facts_service` l'estrazione di "riassunti di conversazione" — alla fine di ogni sessione, estrarre i temi principali discussi e salvarli come fatti ("Abbiamo parlato di Formula 1 il 2026-03-02").

### 6.2 Razza animali nel profilo
Il campo `pets` ha solo `type` (cat/dog) e `name`. Non ha `breed` (razza). Quando Alfio dice "i miei gatti sono di razza europea", questa info finisce in personal_facts ma non nel profilo strutturato.

**Soluzione suggerita**: aggiungere `breed: Optional[str]` al modello `Pet` e gestirlo in `_handle_memory_correction`.

### 6.3 `memory_correction` classificato erroneamente su nuove info
"La mia auto è una Ford Focus" viene classificato come `memory_correction` invece di nuova informazione. Il fix attuale lo gestisce meglio nel handler, ma il classifier continua a sbagliare route.

**Soluzione suggerita**: il `personal_facts_service` in background gestisce comunque questi casi — la risposta è accettabile anche se il route non è perfetto.

### 6.4 Personal facts: nessun limite temporale
I personal_facts non scadono mai (a differenza degli episodes che scadono a 30 giorni). In futuro potrebbe essere utile flaggare fatti "datati" o permettere all'utente di chiedere a Genesi di "dimenticare" qualcosa.

---

## 7. SET DI TEST APPROFONDITI

### BLOCCO A — Personal Facts (feature nuova)

**A1. Salvataggio base cross-session**
```
Sessione 1: "Mia figlia Zoe è stata a Cork in Irlanda per tre settimane"
[riavvio servizio]
Sessione 2: "dove è stata mia figlia?"
ATTESO: risposta che include Cork, Irlanda
LOG: PERSONAL_FACT_SAVED key=zoe_cork_irlanda
```

**A2. Preferenze specifiche non nel profilo**
```
"I miei piloti F1 preferiti sono Leclerc e Hamilton, tifo per la Ferrari"
[dopo qualche messaggio]
"chi tifo nella formula 1?"
ATTESO: Ferrari, Leclerc, Hamilton
LOG: PERSONAL_FACT_SAVED key=f1_piloti_preferiti, key=tifo_ferrari
```

**A3. Abitudini e routine**
```
"di solito ceno alle 20:30 e poi guardo una serie"
[sessione dopo]
"a che ora ceno di solito?"
ATTESO: 20:30
LOG: PERSONAL_FACT_SAVED key=cena_ore_20_30
```

**A4. Correzione con sostituzione (semantic conflict)**
```
"mia figlia studia a Bologna"
[pausa]
"no aspetta, studia a Milano"
[pausa]
"dove studia mia figlia?"
ATTESO: Milano (non "sia Bologna che Milano")
LOG: PERSONAL_FACT_REPLACED old_key=... new_key=...
```

**A5. Riepilogo completo**
```
"cosa sai su di me?"
ATTESO: risposta che include sia profilo strutturato (moglie Rita, figli Ennio e Zoe)
         sia personal facts (piloti F1, orario cena, dove è stata Zoe...)
```

---

### BLOCCO B — Memory Correction (fix critico)

**B1. Aggiunta animale senza perdere gli altri**
```
Profilo ha: gatti Mignolo e Prof
"ho anche un cane, si chiama Rio"
[pausa]
"come si chiamano i miei animali?"
ATTESO: Mignolo, Prof e Rio (tutti e tre)
LOG: MEMORY_CORRECTION_MERGE field=pets added={rio} kept={mignolo, prof}
```

**B2. Negazione non salva come professione**
```
"i miei gatti non sono persiani, sono di razza europea"
[pausa]
"che lavoro fai?"
ATTESO: non risponde "persiani" o "europea"
LOG: COGNITIVE_PROFESSION_SKIP reason=negation
```

**B3. Nuova informazione non genera "Non ho capito"**
```
"La mia auto è una Ford Focus"
ATTESO: risposta positiva come "Capito, hai una Ford Focus!"
NON: "Non ho capito — puoi dirmi più chiaramente cosa cambiare?"
```

**B4. Razza animali corretta**
```
"I miei gatti non sono persiani, sono di razza europea"
[pausa]
"di che razza sono i miei gatti?"
ATTESO: risponde "razza europea" (da personal_facts, non dal profilo)
```

---

### BLOCCO C — Profilo strutturato (guardrail)

**C1. Profession guard — nomi propri**
```
"i miei piloti F1 preferiti sono Leclerc e Hamilton"
[pausa]
"che lavoro fai?"
ATTESO: non risponde "leclerc e hamilton"
LOG: COGNITIVE_PROFESSION_SKIP reason=proper_names_list
```

**C2. Profession guard — "sono nato a"**
```
"sono nato a Catania"
[pausa]
"che lavoro fai?"
ATTESO: non risponde "catania" o "nato a catania"
LOG: COGNITIVE_PROFESSION_SKIP reason=stopword (nato)
```

**C3. Memory correction — figli**
```
Profilo ha: figli Ennio e Zoe
"ho un altro figlio, si chiama Marco"
[pausa]
"come si chiamano i miei figli?"
ATTESO: Ennio, Zoe e Marco (tutti e tre)
```

---

### BLOCCO D — Temporalità e contestualizzazione

**D1. Domanda su cosa abbiamo detto**
```
[dopo aver parlato di Formula 1 e Zoe]
"di cosa abbiamo parlato oggi?"
ATTESO: menziona Formula 1 e/o Zoe/Cork
(usa chat_memory in sessione + personal_facts cross-session)
```

**D2. Riconoscimento temporale**
```
"ieri sono andato a prendere mia figlia all'aeroporto"
[pausa]
"dove è andata mia figlia?"
ATTESO: risponde con Cork o chiede dove è andata
(episode extractor dovrebbe catturare "andata all'aeroporto ieri")
```

**D3. Follow-up automatico su eventi futuri**
```
"la settimana prossima ho un colloquio di lavoro"
[una settimana dopo]
"cosa ho in programma questa settimana?"
ATTESO: Genesi ricorda il colloquio e chiede come è andato
(episode_memory + [puoi chiedere com'è andata])
```

---

### BLOCCO E — Comandi di verifica

**E1. Verifica salvataggio su disco**
```bash
# Su Ubuntu, dopo aver detto qualcosa di personale:
cat /opt/genesi/memory/personal_facts/6028d92a-94f2-4e2f-bcb7-012c861e3ab2.json | python3 -m json.tool
```

**E2. Log monitor completo**
```bash
sudo journalctl -u genesi -f -o cat | grep -E 'PERSONAL_FACT|MEMORY_CORRECTION|COGNITIVE_PROFESSION|EPISODE_SAVED|IDENTITY_ROUTER|CHAT_OUTPUT'
```

**E3. Verifica profilo attuale**
```bash
cat /opt/genesi/memory/profile/6028d92a-94f2-4e2f-bcb7-012c861e3ab2.json | python3 -m json.tool
```

---

## 8. CONSIGLI PER GENESI PRO

### 8.1 Prima di toccare qualsiasi cosa
Leggi SEMPRE questi file prima di modificare:
- `core/proactor.py` — orchestratore centrale, tocca tutto
- `core/personal_facts_service.py` — nuovo layer memoria
- `core/cognitive_memory_engine.py` — estrazione profilo strutturato
- `api/chat.py` — entry point, background tasks

### 8.2 Il principio più importante
**Non aggiungere mai logica di memoria senza chiederti**: "questo dato va nel profilo strutturato, nei personal_facts, negli episodes, o nei global_insights?" La confusione tra layer è la causa di tutti i bug in questa sessione.

### 8.3 I background task devono essere fail-silent
Se un background task fallisce, il chat NON deve interrompersi. Sempre:
```python
async def _do_something_in_background():
    try:
        # logica
    except Exception as e:
        log("SOMETHING_ERROR", error=str(e))
asyncio.create_task(_do_something_in_background())
```

### 8.4 La profession è fragile
Il cognitive_memory_engine usa regex per estrarre la professione. Ogni volta che aggiungi parole italiane che contengono "sono" o "faccio" in contesti non-professionali, potresti generare false positives. Il guard attuale cattura:
- Negazioni ("non sono X")
- Nomi propri multipli ("Leclerc e Hamilton")
- Stopwords ("nato", "razza", etc.)
- Bad starters ("a casa", "in giro", etc.)
- Troppo lungo (> 3 parole)

Se vedi ancora professioni corrotte, aggiungi le parole problematiche a `_PROFESSION_STOPWORDS`.

### 8.5 `memory_correction` è il punto più delicato
È stato il driver di più bug: pets cancellate, city sbagliata, profession corrotta. La causa in tutti i casi era `_call_with_protection` invece di `_call_model`. Se aggiungi nuove logiche qui, usa sempre `_call_model`.

### 8.6 Il profilo di Alfio (utente reale)
```
user_id: 6028d92a-94f2-4e2f-bcb7-012c861e3ab2
email: idappleturrisi@gmail.com
nome: Alfio | città: Imola (ma nel file potrebbe dire Roma)
moglie: Rita | figli: Ennio, Zoe
gatti: Mignolo, Prof (razza europea, non persiana)
cane: Rio
interessi: musica elettronica, techno
F1: tifa Ferrari, piloti preferiti Leclerc e Hamilton
profession: DOVREBBE essere vuota (era corrotta con "persiani" e "leclerc e hamilton")
```

---

## 9. COMMIT HISTORY DI QUESTA SESSIONE

```
35ba340 fix(memory): pets deletion + profession false positives + memory_correction prompt
0904fe4 fix(memory): profession guard for proper names + personal facts conflict resolution
26a7e75 feat(memory): add personal facts layer for cross-session conversational memory
```

---

*Documento generato il 2026-03-02. Branch: gold-faro-stable.*
