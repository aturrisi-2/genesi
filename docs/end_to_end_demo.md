# End-to-End Demo - Cantiere Day

Branch: `operational-memory-mvp`

## Obiettivo

Dimostrare un flusso completo simulato di una giornata WhatsApp di cantiere:

```text
eventi simulati
  -> batch ingest
  -> process pending
  -> stato operativo persistente
  -> snapshot
  -> daily report minimale
```

Non usa WhatsApp reale, OCR reale o dashboard completa.

## Fixture

File:

```text
tests/fixtures/cantiere_day_events.json
```

Contiene 9 eventi:

- messaggi testuali;
- immagine simulata con `simulated_ocr`;
- screenshot simulato con `description`;
- PDF simulato con `simulated_text`;
- documento simulato con `simulated_text`;
- decisioni;
- task assegnati;
- problemi/blocchi;
- domande aperte;
- aggiornamento di task completato.

## Endpoint demo

### Batch ingest

```text
POST /operational-events/{project_id}/batch
```

Input:

```json
{
  "events": []
}
```

Output:

```json
{
  "accepted": 9,
  "duplicates": 0,
  "failed": 0
}
```

### Process pending

```text
POST /operational-events/{project_id}/process-pending
```

### State

```text
GET /operational-state/{project_id}
```

### Snapshot

```text
POST /operational-state/{project_id}/snapshot
GET /operational-state/{project_id}/snapshots
```

### Daily report

```text
GET /operational-state/{project_id}/daily-report
```

## Import offline da export WhatsApp

La demo supporta anche un flusso offline da export `.txt`:

```text
POST /operational-events/{project_id}/import/whatsapp-export
POST /operational-events/{project_id}/process-pending
GET /operational-state/{project_id}/daily-report
```

Fixture:

```text
tests/fixtures/whatsapp_export_sample.txt
```

Questo flusso serve a validare conversazioni reali esportate senza collegamento
live a WhatsApp.

## Cosa valida questa demo

- Gli eventi vengono accettati come stream simulato.
- I duplicati non vengono reinseriti.
- Gli eventi pending vengono processati una sola volta.
- Lo stato persistente cresce con decisioni, task, issue, informazioni e domande.
- Gli allegati simulati contribuiscono allo stato usando testo simulato.
- Si puo salvare una snapshot.
- Si puo generare un daily report derivato dallo stato.

## Limite importante

Il completamento task e ancora euristico e dipende dall'estrazione LLM. Questa
demo mostra il concetto, non una gestione completa del ciclo di vita task.
