# Genesi Legacy Isolation Plan

Reference audit:
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_EXECUTIVE_SUMMARY.md`
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_DEEP_LONG.md`

This is a planning document only. It does not authorize deleting, moving,
migrating, or disabling runtime data. Every isolation step must be handled as a
separate small change with tests and an explicit backup/rollback plan.

## Operating Rules

- Keep production behavior stable while legacy areas are audited.
- Do not move or delete files under `memory/`, `data/`, runtime logs, auth
  stores, media caches, or `/opt/genesi-baileys`.
- Do not change `.env`, project maps, service files, or Baileys runtime during
  legacy isolation.
- Do not enable training, evolution, autopilot, birthday greetings, global group
  greetings, social publishing, or lab automation as part of cleanup.
- Treat static low-reference findings as suspicion, not deletion proof.
- Before moving anything, prove current usage with import search, tests, and
  recent production logs.

## Isolation Candidates

| Area | Evidence | Current risk | Future action |
| --- | --- | --- | --- |
| TTS legacy stack | `tts/`, `tts/tts_api_legacy.py`, `core/tts_provider.py`, `core/tts_sanitizer.py`, wav caches/static test audio | Mixed Edge/Piper/Coqui/OpenAI paths, unclear production contract, heavy assets | Freeze; define one supported TTS provider and archive old assets after backup |
| STT/audio legacy | `api/stt.py`, audio analysis paths, whisper/faster-whisper references | Optional dependencies and unclear live path | Keep off unless explicitly testing voice/audio; add contract tests before refactor |
| Training/autopilot | `core/training_autopilot.py`, `core/training_engine.py`, admin autopilot state | Background side effects, credential-like defaults, subprocess training | Keep disabled; isolate under lab/offline package after proving no startup dependency |
| Evolution engines | `core/auto_evolution_engine.py`, `core/evolution_*`, `data/evolution/*` | Runtime mutation risk and hard-to-test adaptive state | Freeze; document current flags and require explicit product decision before use |
| Lab feedback cycle | `core/lab_feedback_cycle.py`, `lab/global_prompt.json`, `memory/admin/lab_cycle_state.json` | Can mutate prompt/rules and blend with unrelated social feedback | Keep read-only during cleanup; isolate as experimental automation |
| Social publishing | `core/instagram_publisher.py`, Facebook/Instagram/TikTok/OpenClaw social paths | External auth, browser/API fragility, unclear current credentials | Freeze; split into optional integration package after auth/runbook review |
| Moltbook automation | `core/moltbook_service.py`, proactor social routes | Large autonomous/social surface, lab feedback coupling | Keep disabled unless explicitly requested; test routing boundaries before changes |
| OpenClaw/browser automation | `core/openclaw_memory_adapter.py`, proactor social read/setup routes | Desktop/browser dependency not guaranteed on VPS | Keep as non-core; isolate behind capability flag if still needed |
| Vector memory | `core/vector_memory.py`, `data/vectors.db` | Large DB, optional path, low explicit coverage | Do not load or migrate during cleanup; decide whether to keep as product feature |
| Old memory engines | `core/memory_engine_v2.py`, `core/memory_storage.py`, `memory_v2` references | Multiple memory models create confusion and accidental writes | Audit imports and runtime logs; only archive after replacement path is proven |
| Legacy prompt/guard modules | `core/prompt_builder.py`, `core/response_guard.py`, `core/response_handlers.py` | Low references; may be stale alternatives to current proactor/filters | Mark as legacy in docs; add deletion candidate issue only after import/log audit |
| Backups/golden files | `core/llm_service.py.gold`, backup directories/files | Accidental execution or edit confusion | Keep untouched until repository backup/export policy exists |
| Test audio/cache/static generated assets | `test*.wav`, `tts_cache/*`, generated static media | Repo/runtime noise and possible large files | Move only after backup and confirmation that no tests depend on them |

## Verification Checklist Before Any Future Move

For each candidate component:

1. Static usage:
   - `grep -RIn "<module_or_symbol>" core api tests static scripts main.py`
   - `python -m compileall -q core api main.py`
2. Runtime evidence:
   - Search recent logs for module-specific markers.
   - Confirm no startup import or background task depends on it.
3. Test coverage:
   - Add a focused test for the replacement path or for the disabled boundary.
   - Run `scripts/run_safe_baseline_tests.sh`.
4. Data safety:
   - Identify every file under `memory/` or `data/` the component touches.
   - Do not migrate or delete data in the same change.
5. Rollback:
   - Keep the first change documentation-only or import-boundary-only.
   - If files are moved later, preserve a backup path and update imports in one
     small commit.

## Import / Startup Side-Effect Gate

Before a frozen component can be treated as safe to keep in the live tree, it
must pass a no-startup-side-effect gate:

- importing the module must not create async tasks;
- importing the module must not launch subprocesses;
- importing the module must not make HTTP/network requests;
- importing the module must not send Telegram, WhatsApp, Meta, email, or social
  messages;
- importing the module must not write `memory/`, `data/`, `lab/`, or generated
  static assets.

The current guard lives in `tests/test_no_startup_side_effects.py`. It is scoped
to frozen/legacy modules. Existing core boot directory initialization remains a
separate risk and should not be expanded by legacy code.

## Area-Specific Future Steps

### TTS / STT

- Decide whether voice is a live product feature or legacy/demo only.
- If live, define one adapter contract: input text/audio, output file/text,
  failure status, and no uncaught dependency errors.
- Add tests that mock providers and do not require model downloads.
- Only then archive old providers and caches.

### Training / Evolution / Autopilot

- Keep all automatic triggers disabled unless a dedicated task enables them.
- Add a read-only status document that lists flags, storage keys, and side
  effects.
- Move training/evolution runners out of startup paths before deleting anything.
- Require tests proving no background subprocess starts during normal service
  boot.

### Social Publishing / OpenClaw / Moltbook

- Separate user-facing chat intent handling from publishing/automation actions.
- Require explicit capability/config checks before any external call.
- Add tests that social intents fail closed when credentials or browser runtime
  are absent.
- Do not reuse these paths as generic memory or lab input until product policy is
  explicit.

### Vector And Old Memory Systems

- Inventory read/write keys and DB files first.
- Keep current operational memory separate from vector/global memory.
- If vector search remains useful, put it behind an explicit adapter with a
  small contract test and no startup cost.
- If old memory engines are unused, archive after two-step proof: static no-use
  plus logs no-use.

### Legacy Prompt / Response Guards

- Current group pragmatics and response filtering are actively tested elsewhere.
- Do not merge old prompt_builder/response_guard behavior into the live path
  without a precise failing test.
- If retained, document them as historical modules and keep them out of runtime
  routing.

## Do Not Touch Now

- `/opt/genesi-baileys` runtime.
- `.env` and service environment.
- `memory/admin/group_controls.json` outside tested Admin toggles.
- `memory/` and `data/` migrations.
- Birthday/greeting global behavior.
- Training/evolution/autopilot flags.
- Live group mappings and project maps.

## Suggested Sequence

1. Add module banners or docs marking experimental/legacy status.
2. Add no-startup-side-effect tests for training/evolution/lab.
3. Add contract tests for TTS/STT/media before provider cleanup.
4. Add capability checks for social/browser integrations.
5. Archive low-reference modules only after import/log/test proof.
6. Move large runtime artifacts out of deploy scope only with backup and explicit
   operator approval.

## Required Approval For Future Cleanup

Explicit approval is required before:

- deleting files;
- moving files out of the repository;
- changing `.env` or service configuration;
- migrating `memory/` or `data/`;
- touching Baileys runtime;
- enabling any automation currently frozen;
- changing production project maps;
- removing compatibility endpoints.
