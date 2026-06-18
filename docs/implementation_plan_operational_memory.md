# Implementation Plan - Operational Memory

Branch: `operational-memory-mvp`

## Obiettivo

Portare l'MVP da estrazione testuale stateless a primo sistema testabile per
gruppi WhatsApp di cantiere, usando input simulati o export autorizzati.

## Stato attuale

Gia presente:

- endpoint `POST /operational-state`
- modello minimo Decision/Task/Issue/Information/Question
- extractor LLM JSON-only
- test con LLM mockato
- documentazione architetturale iniziale
- automazioni proattive spente sul ramo stabile

## Fase A - Stato persistente testuale

Obiettivo: salvare e aggiornare uno stato operativo per `project_id`.

Deliverable:

- `core/operational_memory/state_store.py`
- `core/operational_memory/state_engine.py`
- endpoint `GET /operational-state/{project_id}`
- endpoint `POST /operational-state/{project_id}/ingest`
- test di merge: nuovo task, task duplicato, task completato, issue chiuso

Regola: nessun input reale WhatsApp in questa fase.

## Fase B - Source model multimodale simulato

Obiettivo: rappresentare testo e allegati in modo uniforme.

Deliverable:

- `SourceItem`
- `Attachment`
- `ExtractionResult`
- supporto input con `source_type`
- provider stub per OCR/vision/document parsing

Esempio:

```json
{
  "project_id": "site_001",
  "sources": [
    {"source_type": "text", "text": "Marco verifica il materiale"},
    {"source_type": "image", "file_name": "foto.jpg", "simulated_ocr": "Mancano 12 pannelli"}
  ]
}
```

## Fase C - Parsing documenti locali

Obiettivo: leggere PDF/DOCX/XLSX caricati manualmente, senza integrazione chat.

Priorita:

1. PDF testuale
2. DOCX
3. XLSX
4. PDF immagine con OCR fallback

## Fase D - Dashboard minima

Obiettivo: consultare lo stato, non chattare.

Vista minima:

- Overview
- Task aperti/completati
- Issues/Risks
- Documenti/immagini
- Timeline
- Export JSON

## Fase E - Daily Digest manuale

Obiettivo: generare un report giornaliero su richiesta a partire dallo stato.

Non inviare automaticamente su WhatsApp.

## Fase F - Snapshot storiche

Obiettivo: salvare snapshot manuali e dopo ogni ingest batch.

Deliverable:

- `snapshot_state(project_id, reason)`
- `events.jsonl`
- confronto tra snapshot

## Elenco rischi

- Sovra-estrazione: il sistema inventa item non presenti.
- Duplicazione: lo stesso task appare piu volte con parole diverse.
- Falsa chiusura: un task viene marcato completato senza conferma.
- Vision fragile: una foto viene interpretata oltre l'evidenza.
- OCR impreciso: numeri, date e misure vengono letti male.
- Privacy: export WhatsApp e allegati possono contenere dati personali.
- Ambiguita responsabilita: molti task non dicono chiaramente chi deve agire.
- Dashboard non usata: se l'utente resta nella chat, il valore non emerge.

## Accuratezza attesa

Target realistico per primo test:

- Task testuali espliciti: 75% precision.
- Decisioni testuali esplicite: 70% precision.
- Issue testuali espliciti: 70% precision.
- PDF testuali: 75% precision sulle informazioni principali.
- Screenshot leggibili: 65% precision.
- Foto cantiere senza testo: sotto 60%, da trattare come descrizione prudente.

Go/no-go iniziale:

- sotto 60% precision su task e decisioni: fermare o riprogettare.
- sopra 75% precision e utenti che consultano dashboard: procedere a canale reale.

## Quali informazioni NON possono essere ricostruite in modo affidabile

- Decisioni dette a voce e mai scritte.
- Responsabilita date per consuetudine ma non esplicitate.
- Priorita non dichiarate.
- Stato complessivo del cantiere da foto parziali.
- Cause tecniche non visibili.
- Misure tagliate, sfocate o lette male.
- Versione corretta di un documento se nel thread circolano piu versioni.
- Intenzioni dietro emoji o risposte vaghe.
- Accordi presi fuori dal gruppo.

## Come validare il sistema con un gruppo WhatsApp reale in meno di 30 giorni

### Settimana 1 - Dataset controllato

- Scegliere un gruppo reale con consenso.
- Esportare 7-14 giorni di chat.
- Rimuovere dati personali non necessari.
- Selezionare 30-50 messaggi/allegati ad alto valore operativo.
- Creare una verita manuale: decisioni, task, issue, informazioni, domande.

### Settimana 2 - Test offline

- Importare il dataset come input simulato.
- Generare stato operativo.
- Confrontare output con verita manuale.
- Misurare precision/recall per categoria.
- Annotare errori ricorrenti.

### Settimana 3 - Dashboard e uso reale assistito

- Mostrare la dashboard/stato a 3-5 persone coinvolte.
- Chiedere di trovare: task aperti, problemi, ultima decisione, documenti.
- Misurare tempo di risposta rispetto alla ricerca nella chat.

### Settimana 4 - Decisione

Continuare solo se:

- almeno 70% precision su task e decisioni;
- gli utenti trovano lo stato piu veloce della chat;
- almeno 3 utenti su 5 dichiarano che lo userebbero ogni settimana;
- gli errori sono correggibili con schema/prompt, non strutturali.

Stop o pivot se:

- il valore emerge solo con integrazioni troppo complesse;
- gli utenti non consultano la dashboard;
- le immagini sono troppo ambigue per sostenere decisioni operative.
