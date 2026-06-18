# Operational State Schema

Branch: `operational-memory-mvp`

## Obiettivo

Definire lo schema dello Stato Operativo Persistente. Questa e l'entita
principale del prodotto.

## Entita principale

```json
{
  "project_id": "site_001",
  "name": "Cantiere Via Roma",
  "status": "active",
  "updated_at": "2026-06-18T10:00:00+02:00",
  "decisions": [],
  "tasks_open": [],
  "tasks_completed": [],
  "issues_open": [],
  "risks": [],
  "information": [],
  "documents": [],
  "images": [],
  "timeline": [],
  "open_questions": [],
  "responsible_parties": []
}
```

## Decision

```json
{
  "id": "dec_...",
  "text": "La consegna viene spostata a mercoledi",
  "status": "active",
  "decided_at": "2026-06-18T09:20:00+02:00",
  "source_ids": ["msg_12"],
  "evidence": "Ok, spostiamo a mercoledi",
  "confidence": 0.88
}
```

## Task

```json
{
  "id": "task_...",
  "text": "Verificare il materiale consegnato",
  "owner": "Marco",
  "due": "venerdi",
  "status": "open",
  "priority": "normal",
  "source_ids": ["msg_13", "img_04"],
  "evidence": "Marco controlli tu il materiale?",
  "confidence": 0.84,
  "created_at": "2026-06-18T09:25:00+02:00",
  "completed_at": null
}
```

## Issue

```json
{
  "id": "issue_...",
  "text": "Fornitura incompleta",
  "status": "open",
  "severity": "medium",
  "source_ids": ["img_05", "msg_18"],
  "evidence": "Mancano 12 pannelli",
  "confidence": 0.82,
  "opened_at": "2026-06-18T10:10:00+02:00",
  "closed_at": null
}
```

## Risk

```json
{
  "id": "risk_...",
  "text": "Possibile ritardo sulla posa per materiale mancante",
  "status": "active",
  "source_ids": ["issue_..."],
  "confidence": 0.62
}
```

## Information

```json
{
  "id": "info_...",
  "text": "Consegna prevista venerdi mattina",
  "source_ids": ["pdf_02"],
  "evidence": "Data consegna: venerdi",
  "confidence": 0.9
}
```

## Document

```json
{
  "id": "doc_...",
  "file_name": "ddt_123.pdf",
  "document_type": "delivery_note",
  "received_at": "2026-06-18T11:00:00+02:00",
  "summary": "DDT consegna pannelli",
  "extracted_text_ref": "extracted/doc_...",
  "linked_items": ["info_...", "issue_..."],
  "confidence": 0.86
}
```

## Image

```json
{
  "id": "img_...",
  "file_name": "foto_materiale.jpg",
  "image_type": "site_photo",
  "received_at": "2026-06-18T11:15:00+02:00",
  "vision_summary": "Materiale accatastato in area esterna",
  "ocr_text": "",
  "linked_items": ["issue_..."],
  "confidence": 0.64
}
```

## Question

```json
{
  "id": "question_...",
  "text": "Chi conferma l'orario di consegna?",
  "status": "open",
  "source_ids": ["msg_21"],
  "evidence": "A che ora arrivano?",
  "confidence": 0.92
}
```

## Timeline Event

```json
{
  "id": "event_...",
  "timestamp": "2026-06-18T11:20:00+02:00",
  "event_type": "task_created",
  "text": "Task assegnato a Marco",
  "related_item_ids": ["task_..."],
  "source_ids": ["msg_13"]
}
```

## Merge rules

- Nuovi task simili non devono duplicare task esistenti.
- Una conferma di completamento chiude il task solo se la fonte e chiara.
- Una decisione successiva puo sostituire una decisione precedente.
- Un issue resta aperto finche non c'e evidenza di risoluzione.
- Ogni modifica deve generare un evento timeline.

## Persistenza

MVP persistente:

```text
memory/operational_state/{project_id}.json
memory/operational_state/{project_id}/sources/{source_id}.json
memory/operational_state/{project_id}/snapshots/{timestamp}.json
```

La persistenza deve essere file-based inizialmente, coerente con il repo, e
potra evolvere in database solo dopo validazione.
