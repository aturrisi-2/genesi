# Multimodal Pipeline

Branch: `operational-memory-mvp`
Scope: WhatsApp cantiere, input simulati nella prima fase

## Obiettivo

Progettare una pipeline modulare che trasformi messaggi, immagini, screenshot,
PDF e documenti in Stato Operativo Persistente.

Il Daily Digest non e il prodotto. E solo una vista derivata dello stato.

## Pipeline

```text
Input
  |
  v
Content Classification
  |
  v
Text/OCR/Document/Vision Extraction
  |
  v
Information Extraction
  |
  v
Operational Classification
  |
  v
Operational State Engine
  |
  v
Persistent Operational State
```

## Componenti

### 1. Input Adapter

Responsabilita:

- ricevere messaggi simulati in MVP
- normalizzare ogni elemento in un formato comune
- preservare metadati: autore, timestamp, chat_id, file_name, mime_type

Formato concettuale:

```json
{
  "id": "source_001",
  "source_type": "text|image|pdf|docx|xlsx",
  "author": "Marco",
  "timestamp": "2026-06-18T09:15:00+02:00",
  "text": "...",
  "file_path": "...",
  "metadata": {}
}
```

### 2. Content Classification

Classifica il contenuto prima di analizzarlo:

- testo semplice
- immagine generica
- immagine con testo
- screenshot
- foto documento
- tabella fotografata
- PDF testuale
- PDF scansionato
- documento Office
- cronoprogramma
- report avanzamento

Output:

```json
{
  "content_type": "photo_document",
  "requires_ocr": true,
  "requires_vision": true,
  "requires_table_extraction": false,
  "confidence": 0.78
}
```

### 3. OCR

Scopo: estrarre testo da immagini, screenshot, scansioni PDF.

Opzioni:

- OCR locale: piu privato, meno costo, accuratezza variabile.
- OCR cloud: migliore su documenti difficili, ma privacy/costo.
- GPT multimodale: utile per testo + contesto visivo, costo maggiore.
- Ibrido: OCR locale prima, fallback multimodale se confidenza bassa.

Raccomandazione MVP:

- progettare interfaccia astratta `OcrProvider`
- implementare inizialmente un provider stub/simulato
- aggiungere OCR reale solo dopo dataset di test

### 4. Vision Analysis

Scopo: capire cosa mostra una foto, non solo leggere testo.

Esempi:

- "pallet consegnati in area esterna"
- "tubo danneggiato evidenziato da freccia rossa"
- "massetto non completato"
- "foto di cronoprogramma appeso in cantiere"

Nota critica: la vision non deve trasformare interpretazioni in fatti certi.
Ogni output deve avere confidenza e possibilmente una descrizione prudente.

### 5. Document Extraction

Scopo: estrarre testo e strutture da PDF/DOCX/XLSX.

Percorso:

- PDF testuale: parser diretto
- PDF immagine: OCR fallback
- DOCX: testo, tabelle, titoli
- XLSX: fogli, celle, righe, intestazioni
- immagini embedded: invio a OCR/vision

### 6. Information Extraction

Trasforma testo estratto e descrizioni visive in candidate facts:

```json
{
  "text": "Marco deve verificare il materiale entro venerdi",
  "evidence": "msg 12",
  "source_id": "source_012",
  "confidence": 0.86
}
```

### 7. Operational Classification

Mappa ogni candidate fact in:

- Decision
- Task
- Issue
- Information
- Question

Ogni item deve conservare:

- source_id
- evidence
- confidence
- extraction_method

### 8. Operational State Engine

Responsabilita:

- inserire nuovi item
- aggiornare item esistenti
- chiudere task completati
- collegare documenti e immagini agli item
- mantenere timeline
- creare snapshot storiche

## Piano implementativo

### Step 1 - Documentazione e schema

Creare i documenti di architettura e lo schema persistente dello stato.

### Step 2 - Input simulato multimodale

Estendere l'MVP attuale da `messages: list[str]` a una struttura che possa
descrivere testi e allegati simulati, senza leggere ancora WhatsApp reale.

### Step 3 - State Engine persistente

Implementare salvataggio e merge dello stato operativo per `project_id`.

### Step 4 - Provider stub

Creare interfacce per OCR/document/vision e provider simulati per test.

### Step 5 - PDF/DOCX/XLSX locali

Aggiungere parsing file locali caricati manualmente.

### Step 6 - Dashboard minima

Vista consultabile dello stato, con filtri e export.

### Step 7 - Validazione reale controllata

Usare un export WhatsApp reale, autorizzato e anonimizzato, senza integrazione
automatica in produzione.

## Rischi

- Troppe fonti troppo presto.
- Output multimodale non verificabile.
- Costi elevati su immagini/documenti.
- Privacy e consenso nei gruppi.
- Tabelle e cronoprogrammi molto difficili.
- Dashboard che diventa archivio confuso invece di fonte di verita.

## Accuratezza attesa

Nel primo MVP multimodale non bisogna promettere piu del 60-70% su fonti miste.
Il sistema deve mostrare confidenza e fonte, non fingere certezza.
