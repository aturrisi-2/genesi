# Genesi Runtime Risks

Reference audit:
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_EXECUTIVE_SUMMARY.md`
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_DEEP_LONG.md`

## High Priority Risks

| Risk | Current status | Mitigation |
| --- | --- | --- |
| Baileys runtime is outside repo | `genesi-baileys.service` runs `/opt/genesi-baileys/index.js` | Never patch live runtime casually; document and sync deliberately |
| Runtime data inside repo tree | dirty/untracked runtime files appear in `/opt/genesi` | Never use `git add .`; stage exact files only |
| Admin group controls are critical | `memory/admin/group_controls.json` controls visible group replies | Writes are atomic as of `fix(admin): write group controls atomically`; keep tests |
| Admin fallback legacy records | fallback records may miss fields | Summary/download tolerate missing/extra fields as of `fix(admin): tolerate missing group key in fallback summary` |
| External credentials | logs showed Google `invalid_grant`; other integrations depend on env | Do not edit env in code cleanup; document boolean health separately |
| Broad automation flags | birthday/greeting/training/evolution can be noisy if enabled globally | Keep proactive/global automations frozen unless requested |

## Production Rules

- No manual deploy/restart unless explicitly authorized.
- No live POSTs from cleanup tasks.
- No live messages to WhatsApp/Telegram groups.
- No environment edits from repo work.
- No Baileys runtime edits from backend work.
- No cleanup of real memory/data without backup and explicit approval.

## Known Dirty/Runtime Files

These files have appeared as dirty/untracked during audits and must not be committed as part of cleanup unless the task explicitly targets them:

- `genesi_graph.json`
- `monitor_trigger_count.txt`
- `.venv/`
- `genesi/ai_engineer_os/logs/coding_observations_2026-03-01.json`
- `static/ig_posts/`

## Core Import Side Effects

Some core modules initialize local runtime directories when imported or when
their global singleton is created. This is current behavior, not a new cleanup
target.

| Module | Import-time behavior | Classification | Test coverage |
| --- | --- | --- | --- |
| `core.storage` | creates `memory/short_term_chat`, `memory/long_term_profile`, `memory/relational_state`, `memory/semantic_facts`, `memory/episodes` | acceptable if confined to configured/current working path; future lazy-init candidate | `tests/test_core_import_side_effects.py` |
| `auth.config` | creates `data/auth` and builds SQLite URL | acceptable boot prerequisite if confined to configured/current working path; future lazy-init candidate | `tests/test_core_import_side_effects.py` |
| `core.fallback_engine` | creates/loads `memory/admin/fallbacks.json` path via singleton | acceptable monitoring boot behavior if confined; legacy records must stay tolerated | `tests/test_core_import_side_effects.py` |
| `core.document_memory` | creates `memory/documents` at import | acceptable but should become lazy-init in a future focused cleanup | `tests/test_core_import_side_effects.py` |
| `core.reminder_engine` | creates `data/reminders` through global singleton | acceptable boot behavior for reminder subsystem; future lazy-init candidate | `tests/test_core_import_side_effects.py` |

The tests monkeypatch the current working directory to `tmp_path` and verify
that importing these modules does not alter real `/opt/genesi/memory` or
`/opt/genesi/data` files. Do not expand this pattern casually; new modules
should avoid import-time writes unless there is a clear boot contract.

## Web TTS/STT

TTS and STT are Web app features, not group features. The active Web paths are
`POST /api/tts/` and `POST /api/stt/`, both protected by JWT. They must not be
connected to WhatsApp, Telegram, Baileys, or automatic group audio replies.

Current decision: keep them Web feature-gated. The static contract is coherent,
and endpoint tests with mocked providers cover auth, payloads, controlled
provider errors, and separation from group bridges. Recent production logs still
do not confirm Web TTS/STT usage with real providers. See
`docs/web_tts_stt_status.md`.

Audio/cache cleanup must start from `docs/audio_cache_inventory.md`: files in
`tts_cache/`, `data/tts*`, `static/voice_test/`, `voice_tests/`, and
`voice_gold/` are candidates only after backup, manifest, and explicit approval.

## Verification After Each Promotion

Use non-mutating checks only:

```bash
git fetch origin --prune
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/gold-faro-stable
systemctl is-active genesi.service
systemctl is-active genesi-baileys.service
journalctl -u genesi.service --since "15 minutes ago" --no-pager \
  | grep -aE "Application startup complete|Traceback|ImportError|ERROR" \
  | tail -220
```
