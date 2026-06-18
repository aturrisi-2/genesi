# WhatsApp Export Importer

Branch: `operational-memory-mvp`

## Obiettivo

Importare offline un file `.txt` esportato da WhatsApp e trasformarlo in
`OperationalEvent` pending.

Non e una integrazione live. Non invia messaggi. Non crea bot.

## Endpoint

```text
POST /operational-events/{project_id}/import/whatsapp-export
```

Input:

```json
{
  "raw_text": "...",
  "source_name": "gruppo-cantiere-demo",
  "timezone": "Europe/Rome"
}
```

Output:

```json
{
  "project_id": "site-wa",
  "source_name": "gruppo-cantiere-demo",
  "parsed": 8,
  "accepted": 8,
  "duplicates": 0,
  "ignored": 2,
  "failed": 0
}
```

## Formati supportati

```text
[18/06/26, 07:42:13] Marco: testo messaggio
18/06/2026, 07:42 - Marco: testo messaggio
18/06/26, 07:42 - Marco: testo messaggio
```

## Gestione parser

Supporta:

- messaggi multilinea;
- messaggi senza autore ignorati;
- messaggi di sistema ignorati;
- media omessi;
- `<attached: ...>`;
- normalizzazione timestamp con timezone;
- `event_id` stabile da `project_id + timestamp + sender + content`.

## Media omessi

I media non vengono letti davvero. Vengono importati come eventi simulati:

- `image` per `<Media omessi>` / `media omitted`;
- `pdf` se il marker contiene `.pdf`;
- `document` se il marker contiene `.docx`, `.xlsx`, ecc.

L'evento resta pending e potra essere processato dal watcher. In questa fase
l'allegato ha solo descrizione simulata.

## Flusso corretto

```text
Import export WhatsApp
  -> eventi pending
  -> process-pending manuale
  -> Stato Operativo Persistente
  -> daily report / snapshot
```

## Fixture

```text
tests/fixtures/whatsapp_export_sample.txt
```

Include messaggi normali, multilinea, media omessi, PDF simulato, messaggi di
sistema, decisioni, task, problemi e domande aperte.

## Vincoli

- Nessun WhatsApp live.
- Nessun bot.
- Nessun invio messaggi.
- Nessun OCR reale.
- Nessun processing automatico dopo import.
