# Operational Memory — Storage, VPS readiness & simulated-group test plan

Scope: the `operational-memory-mvp` branch. Generic, global, multimodal,
adaptive to any chat/profession. No domain hardcoding. Genesi is a **silent
presence**: it always listens/stores/updates memory and replies only on explicit
invocation.

## 1. Storage layout (local / VPS)

All operational state lives under `memory/` (git-ignored via `memory/*`), so it
is local, controlled and backup-friendly. One JSON tree per concern, sharded by
`project_id` (the chat/group identity):

| Concern | Path | Idempotent | Retention |
| --- | --- | --- | --- |
| Raw + normalized events | `memory/operational_events/{project}.json` | yes (event_id dedup) | full history (append, no dup) |
| Operational state | `memory/operational_state/{project}.json` | yes (last write wins) | single current state |
| Incremental index | `memory/operational_indexes/{project}_incremental.json` | yes | single current index |
| Long-export checkpoints | `memory/operational_checkpoints/{project}_long_export.json` | yes | single current checkpoint |
| Lifecycle snapshots (FASE 4.3) | `memory/operational_lifecycle_snapshots/{project}/` | yes | **30** (pruned, `DEFAULT_LIFECYCLE_SNAPSHOT_RETENTION`) |
| Legacy full snapshots | `memory/operational_snapshots/{project}/` | yes | unbounded (manual/admin) |
| Reports (FASE 7) | `memory/operational_reports/{project}/` | yes | **50** (pruned, `DEFAULT_REPORT_RETENTION`) |

Notes:
- **Idempotency**: `event_store` dedups by `event_id`; re-ingesting the same
  message is a no-op. The pipeline is incremental (FASE 3) — small batches do not
  trigger a full rebuild.
- **Retention**: reports and lifecycle snapshots are pruned on write. Events and
  the current state are intentionally kept (state is a single file; events are the
  source of truth and stay deduped).
- **No DB**: storage is plain JSON on disk. No Postgres/SQLite introduced. Moving
  to a DB is a future, separate decision — not required for VPS test.
- **Temp files**: none left by the pipeline. Validation/demo projects can be
  removed by deleting their per-project files/dirs above.

### VPS readiness checklist
- Ensure the service working directory is writable and `memory/` persists across
  restarts (and is included in backups).
- Paths are centralized as module-level `_BASE_DIR` constants — overridable in
  tests via monkeypatch; for the VPS the defaults under `memory/` are correct.
- Retention is finite for the two growing stores (reports, lifecycle snapshots).
- Health checks: `HEAD`/`GET` on `/api/operational/projects/{id}/reports/{rid}/view`
  and `/download` (HEAD added in FASE 9a) for link/monitor probes.

## 2. Simulated-group test plan (NEXT cycle — preparation only)

Goal: validate Genesi-as-chat-presence on a real group surface, **without**
re-injecting historical messages into a new chat.

Principle:
- The **real history is imported into Genesi as memory/dataset** (already done for
  the validation project, e.g. via the WhatsApp export importer / `ingest-test`).
- The **test group is only an invocation surface**. It does NOT need to contain
  the whole history. Members chat normally; Genesi stays silent until invoked.
- When invoked, Genesi answers from the memory/state already built from the
  imported history.

Suggested setup:
- 3 presences: Alfio, a second Alfio account, and Genesi.
- Channels (by increasing realism / constraint):
  1. **Harness** (`/operational/harness`) — already available; pure logic validation.
  2. **Telegram test group** — easiest bot/group prototype.
  3. **WhatsApp test group** — closest to the final target, gated by official API.

Flow to validate:
1. Import a real history into Genesi's operational memory under a `project_id`.
2. In the test group, send normal messages → Genesi stays **silent**, memory updates.
3. Invoke ("Genesi, fammi il punto" / "@genesi cosa resta aperto?") → Genesi replies
   with the compact table + synthesis + report link, using the imported history.
4. Open the report link (view), download, print.

Do **not** implement the Telegram/WhatsApp integration in this cycle — this is a
plan only. Default stays silent; no proactive messages; no LLM decides when to
speak.
