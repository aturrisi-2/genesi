# Offline Validation Flow

Branch: `operational-memory-mvp`

## Obiettivo

Validare l'idea di Operational Memory usando un export WhatsApp testuale
anonimizzato, senza integrare WhatsApp reale e senza avviare automazioni.

Il flusso offline permette di incollare una conversazione esportata e ottenere
in un solo passaggio:

- eventi operativi normalizzati;
- processing degli eventi pending;
- aggiornamento dello stato operativo persistente;
- snapshot opzionale;
- report operativo in markdown.

## Endpoint

```text
POST /operational-demo/{project_id}/whatsapp-export/run
```

## Request

```json
{
  "raw_text": "12/06/26, 08:31 - Marco: manca il materiale in cantiere",
  "source_name": "gruppo-cantiere-reale-anonimizzato",
  "timezone": "Europe/Rome",
  "create_snapshot": true,
  "report_format": "markdown"
}
```

Campi:

- `raw_text`: contenuto dell'export WhatsApp `.txt`;
- `source_name`: nome sicuro della sorgente, default `whatsapp-export`;
- `timezone`: timezone usata per interpretare le date, default `Europe/Rome`;
- `create_snapshot`: se `true`, salva una snapshot dopo il processing;
- `report_format`: `markdown` oppure `json`.

Se `raw_text` e vuoto o contiene solo spazi, l'endpoint risponde con `400`.

## Response

```json
{
  "project_id": "site-demo",
  "import": {
    "parsed": 8,
    "accepted": 8,
    "duplicates": 0,
    "ignored": 0,
    "failed": 0
  },
  "processing": {
    "processed": 8,
    "failed": 0,
    "pending_after": 0
  },
  "snapshot": {
    "created": true,
    "snapshot_id": "snap_site-demo_20260618T062853"
  },
  "state_counts": {
    "decisions": 1,
    "open_tasks": 3,
    "completed_tasks": 0,
    "issues": 2,
    "information": 3,
    "questions": 1
  },
  "daily_report_markdown": "## Operational Daily Report..."
}
```

Con `report_format: "json"` la risposta include anche `daily_report_json`.

## Pipeline

```text
raw WhatsApp export
  -> parse_whatsapp_export
  -> ingest_events_batch
  -> process_pending_events
  -> create_snapshot
  -> build_daily_report
```

La deduplica avviene sugli `event_id` deterministici prodotti
dall'importatore. Eseguire due volte lo stesso export nello stesso `project_id`
non reinserisce gli eventi gia presenti e non rielabora quelli gia processati.

## Confini di sicurezza

Questo flusso non:

- si collega a WhatsApp reale;
- ascolta webhook;
- invia messaggi;
- esegue OCR reale;
- pubblica contenuti;
- richiede dashboard.

E un validatore offline: serve a capire se da conversazioni reali anonimizzate
emerge uno stato operativo utile.

## Come usarlo per validazione prodotto

1. Esporta una chat WhatsApp come `.txt`.
2. Anonimizza nomi, numeri, luoghi sensibili e dati personali.
3. Invia il testo all'endpoint demo.
4. Leggi `state_counts` per capire quanto segnale operativo e stato estratto.
5. Leggi `daily_report_markdown` come output valutabile da un utente reale.
6. Ripeti su piu conversazioni e confronta utilita, errori e mancanze.

L'obiettivo non e dimostrare che il parser e perfetto. L'obiettivo e verificare
se il report prodotto aiuta davvero una persona a capire rapidamente cosa sta
succedendo.
