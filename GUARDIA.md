# 🛡️ GENESI GUARDIAN - Protocollo Anti-Regressione

Questo documento definisce il "Semaforo di Stabilità" di Genesi. Ogni modifica al codice deve essere filtrata attraverso queste Skill per garantire che il progetto possa solo progredire, mai regredire.

---

## 🚦 IL SEMAFORO DELLE SKILL

### 🔴 AREA ROSSA: Skill Critiche (Rischio Regressione Totale)
*Le modifiche in quest'area richiedono test manuali completi del ciclo di interazione.*

#### 1. Ciclo di Conversazione Naturale & Voce
- **Organi (File):** `static/app.v2.js`, `core/proactor.py`, `core/llm_service.py`, `core/tts_provider.py`
- **Paletti:** 
  - Il microfono deve riattivarsi automaticamente dopo ogni risposta di Genesi.
  - Nessun feedback loop (Genesi non deve ascoltare se stessa mentre parla).
  - La risposta deve essere fluida e coerente col tono impostato.
- **Test:** Messaggio vocale -> Risposta vocale completa -> Mic torna in ascolto (Orb blu).

#### 2. Memoria, Identità & Proattività
- **Organi (File):** `core/memory_consolidation.py`, `core/episodic_memory.py`, `core/identity_extractor.py`, `core/storage.py`
- **Paletti:**
  - I dati dell'utente (profilo, preferenze) non devono mai essere sovrascritti erroneamente.
  - La memoria a lungo termine deve essere richiamabile durante la chat.
- **Test:** Chiedere dettagli personali salvati in sessioni precedenti.

---

### 🟡 AREA GIALLA: Skill Avanzate (Rischio Regressione Funzionale)
*Le modifiche in quest'area possono compromettere strumenti specifici.*

#### 3. Upload, Visione & OCR
- **Organi (File):** `api/upload.py`, `core/file_analyzer.py`, `core/ocr_service.py`
- **Paletti:**
  - Le immagini non devono causare troncamenti nella conversazione.
  - La trascrizione OCR deve essere accurata e integrata nel contesto della chat.
- **Test:** Caricare un'immagine con testo -> Genesi deve commentarla correttamente senza "perdersi".

#### 4. Auto-Tuning & Evoluzione
- **Organi (File):** `core/auto_evolution_engine.py`, `core/auto_tuner.py`, `core/evolution_state_manager.py`
- **Paletti:**
  - Il sistema di apprendimento non deve creare loop infiniti di feedback o alterare la personalità bruscamente.
- **Test:** Verifica log evoluzione dopo 12 ore di attività.

#### 5. Sincronizzazione Ecosistema (Google/iCloud)
- **Organi (File):** `api/calendar_auth.py`, `core/icloud_service.py`, `api/user.py`
- **Paletti:**
  - Il pop-up di configurazione non deve essere bloccante (deve essere chiudibile).
  - I token OAuth devono persistere correttamente al riavvio del server.
- **Test:** Ricarica pagina -> Pop-up appare/scompare correttamente -> Eventi sincronizzati.

---

### 🟢 AREA VERDE: Skill Estetiche & Interfaccia
*Modifiche sicure, impatto limitato alla visualizzazione.*

#### 6. UI/UX & PWA
- **Organi (File):** `static/style.css`, `static/index.html`, `static/sw.js`
- **Paletti:**
  - Layout responsivo su iOS/Android e Desktop.
  - Il Service Worker deve rimanere attivo per le notifiche push.
- **Test:** Verifica rendering su mobile e registrazione SW nelle impostazioni.

---

## 📜 PROTOCOLLO D'AZIONE PER L'AI
1. **Analisi:** Prima di modificare un file, identificare il colore dell'area nel documento.
2. **Avviso:** Se l'area è ROSSA o GIALLA, dichiararlo esplicitamente nell'anteprima del lavoro.
3. **Verifica:** Dopo il deploy, eseguire i test manuali descritti nella colonna "Test".
4. **Validazione:** Confermare al USER che le skill protette sono ancora attive e funzionanti.

---
*Documento creato il: 26 Febbraio 2026 - Versione 1.0 (Gold Stable)*
