# Historical Snapshots

Branch: `operational-memory-mvp`

## Obiettivo

Permettere audit, ricostruzione eventi e analisi temporale dello stato
operativo.

Domande target:

- Qual era lo stato il giorno X?
- Quando e stato assegnato un task?
- Quando e cambiata una decisione?
- Come si e evoluto il progetto?
- Quando e comparso un problema?
- Quando e stato chiuso?

## Snapshot

Uno snapshot e una copia immutabile dello Stato Operativo in un momento dato.

Formato:

```json
{
  "snapshot_id": "snap_2026-06-18T18-00-00",
  "project_id": "site_001",
  "created_at": "2026-06-18T18:00:00+02:00",
  "reason": "daily|manual|before_merge|after_import",
  "state": {}
}
```

## Quando salvare

MVP:

- manualmente
- dopo ogni import batch
- prima di una modifica rilevante

Post-MVP:

- giornalmente
- a fine giornata lavorativa
- prima/dopo merge automatici

## Event log

Oltre agli snapshot serve una timeline append-only:

```json
{
  "event_id": "event_...",
  "timestamp": "2026-06-18T12:00:00+02:00",
  "project_id": "site_001",
  "event_type": "task_status_changed",
  "item_id": "task_...",
  "before": {"status": "open"},
  "after": {"status": "completed"},
  "source_ids": ["msg_44"]
}
```

## Differenze tra stati

Il sistema deve poter calcolare:

- item aggiunti
- item rimossi
- item modificati
- task aperti/chiusi
- decisioni sostituite
- issue aperti/chiusi

## Persistenza

Percorso iniziale:

```text
memory/operational_state/{project_id}/snapshots/{snapshot_id}.json
memory/operational_state/{project_id}/events.jsonl
```

JSONL per eventi append-only. JSON per snapshot completi.

## Rischi

- Troppi snapshot possono crescere rapidamente.
- Snapshot senza eventi rendono difficile spiegare il perche di una modifica.
- Eventi senza snapshot rendono difficile ricostruire lo stato se ci sono bug.

## Strategia

Usare entrambi:

- snapshot per recupero rapido
- event log per spiegabilita

## Validazione in meno di 30 giorni

Usare un export WhatsApp reale autorizzato:

1. Importare un thread storico.
2. Creare stato giorno per giorno.
3. Salvare snapshot giornalieri.
4. Chiedere agli utenti se la ricostruzione corrisponde alla realta.
5. Misurare errori su task, decisioni e problemi.
