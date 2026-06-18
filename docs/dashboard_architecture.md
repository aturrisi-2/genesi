# Dashboard Architecture

Branch: `operational-memory-mvp`

## Obiettivo

La dashboard deve diventare la fonte di verita operativa del gruppo WhatsApp di
cantiere. La chat resta canale di comunicazione, non archivio operativo.

## Principi

- Mostrare stato, non conversazione.
- Ogni item deve essere verificabile dalla fonte.
- Filtri e ricerca sono piu importanti dell'estetica.
- Nessuna proattivita automatica nella prima fase.
- Export sempre disponibile.

## Viste minime

### 1. Overview

Contiene:

- stato progetto
- ultimo aggiornamento
- task aperti
- problemi aperti
- decisioni recenti
- domande aperte
- documenti recenti

### 2. Task

Campi:

- testo
- owner
- due
- status
- source
- confidence

Filtri:

- owner
- status
- scadenza
- priorita

### 3. Issues/Risks

Campi:

- problema
- severita
- stato
- fonte
- item collegati

### 4. Documents

Campi:

- nome file
- tipo documento
- data ricezione
- sintesi
- informazioni estratte
- link a item operativi

### 5. Images

Campi:

- anteprima
- tipo immagine
- descrizione vision
- testo OCR
- item collegati
- confidenza

### 6. Timeline

Elenco eventi:

- task creato
- task completato
- decisione presa
- problema aperto/chiuso
- documento ricevuto
- domanda aperta/risolta

### 7. Search

Ricerca su:

- testo item
- evidenze
- nomi documenti
- OCR
- vision summaries
- responsabili

## Struttura dati frontend

La dashboard deve leggere un unico endpoint concettuale:

```text
GET /operational-state/{project_id}
```

Output:

```json
{
  "project": {},
  "summary": {},
  "decisions": [],
  "tasks_open": [],
  "tasks_completed": [],
  "issues_open": [],
  "risks": [],
  "documents": [],
  "images": [],
  "timeline": [],
  "open_questions": []
}
```

## Export

Formati:

- PDF stato corrente
- JSON completo
- CSV task
- CSV issues

## Mockup architetturale

```text
Left navigation
  Overview
  Tasks
  Issues
  Documents
  Images
  Timeline
  Search

Main panel
  Filters
  Operational list/table
  Source evidence drawer

Right drawer
  Original message/document/image evidence
  Extraction confidence
  Linked items
```

## Cosa NON fare ora

- Non costruire una UI sofisticata.
- Non inserire chat live.
- Non aggiungere avatar o assistant persona.
- Non aggiungere notifiche.
- Non ottimizzare per branding.

La prima dashboard deve essere uno strumento di lavoro: denso, leggibile,
filtrabile, esportabile.
