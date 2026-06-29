# Genesi Legacy And Frozen Components

Reference audit:
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_EXECUTIVE_SUMMARY.md`
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_DEEP_LONG.md`

This document lists components that exist in the repository but should be treated as legacy, frozen, partial, or lab-only until a dedicated stabilization task proves otherwise.

## Freeze By Default

| Area | Evidence / files | Current decision |
| --- | --- | --- |
| Training / autopilot / evolution | `core/training_autopilot.py`, `core/auto_evolution_engine.py`, `core/evolution_*` | Keep off unless explicitly requested; do not enable during cleanup |
| Legacy TTS/STT stacks | `tts/`, `core/tts_provider.py`, `api/stt.py`, audio caches | Freeze; validate with a separate media/audio task |
| Social publishing / browser automation | `core/facebook_service.py`, `core/instagram_publisher.py`, integration modules | Freeze; high external dependency and auth risk |
| iCloud / Google integrations | `core/integrations/`, reminder/calendar code | Freeze until credentials and failure mode are documented |
| OpenClaw / desktop send | `core/openclaw_memory_adapter.py`, related proactor paths | Freeze; do not rely on it for production cleanup |
| Lab / feedback automation | `core/lab_feedback_cycle.py`, lab/admin endpoints | Keep read-only unless explicitly stabilizing it |
| Old memory engines | `core/memory_engine_v2.py`, `core/memory_storage.py`, vector memory/data | Do not remove yet; isolate after import/use audit |
| Golden/backup code | `core/llm_service.py.gold`, backup files/directories | Do not execute or refactor casually |

## Likely Dead Or Low-Reference Modules

The audit found modules with zero or very low static references. Treat these as suspects, not proof of deletion safety:

- `core/context_signal_analyzer.py`
- `core/memory_engine_v2.py`
- `core/prompt_builder.py`
- `core/response_guard.py`
- `core/response_handlers.py`
- `api/proactor_api.py`
- `api/system_diagnostics.py`
- `core/emoji_filter.py`
- `core/emotion_adapter.py`
- `core/tts_sanitizer.py`

Before removing any of them:

1. Run static import search.
2. Run runtime grep in logs if relevant.
3. Add or update tests proving the replacement path.
4. Move only after backup/approval.

## Cleanup Boundaries

Do not physically delete, move, or migrate any of the following during structural cleanup:

- `memory/`
- `data/`
- runtime logs
- auth stores
- media caches
- `/opt/genesi-baileys`
- `.env` or environment files
- model files
- user-uploaded/static generated assets

