# Watcher Engine

Branch: `operational-memory-mvp`

## Obiettivo

Trasformare l'MVP da tool manuale on-demand a osservatore permanente simulato.

In questa fase non esiste integrazione WhatsApp reale. Il sistema riceve eventi
simulati, li salva in uno storico locale, processa quelli pending e aggiorna lo
Stato Operativo Persistente.

## OperationalEvent

Schema:

```json
{
  "event_id": "evt_001",
  "project_id": "site_001",
  "source": "simulated-whatsapp",
  "sender": "Marco",
  "timestamp": "2026-06-18T08:00:00+00:00",
  "type": "text",
  "content": "Marco verifica il materiale domani",
  "attachment_metadata": {},
  "processed_status": "pending"
}
```

Campi:

- `event_id`: identificatore stabile evento.
- `project_id`: progetto/cantiere.
- `source`: origine simulata, poi adapter reale.
- `sender`: autore.
- `timestamp`: timestamp evento.
- `type`: `text`, `image`, `pdf`, `document`.
- `content`: testo principale o descrizione simulata.
- `attachment_metadata`: metadati allegato, inclusi `simulated_ocr` o `simulated_text`.
- `processed_status`: `pending`, `processed`, `failed`.

## Event Ingestion Layer

Responsabilita:

- ricevere eventi grezzi;
- normalizzare contenuto, sender e source;
- deduplicare per `event_id`;
- salvare in coda/storico locale.

Persistenza MVP:

```text
memory/operational_events/{project_id}.json
```

## Watcher Engine

Responsabilita:

1. Leggere eventi del progetto.
2. Filtrare solo `processed_status=pending`.
3. Convertire ogni evento in messaggio di estrazione.
4. Passare il messaggio all'extraction/state engine.
5. Aggiornare lo Stato Operativo Persistente.
6. Marcare evento `processed`.
7. Marcare evento `failed` in caso di errore.

## Gestione allegati simulati

Per immagini/PDF/documenti non si usa OCR reale. Si leggono campi simulati:

- `attachment_metadata.simulated_ocr`
- `attachment_metadata.simulated_text`
- `attachment_metadata.description`

Questo consente di testare la pipeline senza integrare OCR o WhatsApp reale.

## Endpoint

```text
POST /operational-events/{project_id}
GET /operational-events/{project_id}
POST /operational-events/{project_id}/process-pending
GET /operational-state/{project_id}
```

## Futuro adapter WhatsApp

In futuro WhatsApp reale dovra solo produrre `OperationalEvent`.

L'adapter non dovra conoscere lo state engine. Il contratto rimane:

```text
WhatsApp Adapter -> OperationalEvent -> Event Store -> Watcher Engine -> Operational State
```

## Cosa NON fa ora

- Non ascolta WhatsApp reale.
- Non esegue OCR reale.
- Non analizza immagini reali.
- Non invia notifiche.
- Non genera digest automatici.
- Non costruisce dashboard completa.

## Test coperti

- ingestione evento testuale;
- deduplica per `event_id`;
- processing pending;
- aggiornamento stato persistente;
- evento gia processato non rielaborato;
- allegato immagine simulato tramite `simulated_ocr`.
