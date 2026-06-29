# Genesi Live Components

Reference audit:
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_EXECUTIVE_SUMMARY.md`
- `/tmp/genesi_deep_audit_20260628_092725/AUDIT_GENESI_DEEP_LONG.md`

This document lists the components considered part of the current production core. Keep changes to these areas small, tested, and deployable through `gold-faro-stable`.

## Production Branch And Services

- Production branch: `gold-faro-stable`.
- Runtime repository: `/opt/genesi`.
- Backend service: `genesi.service`.
- WhatsApp bridge service: `genesi-baileys.service`.
- Baileys live runtime is outside this repository at `/opt/genesi-baileys`; do not edit it from normal backend work.

## Reliable Core

| Component | Main files | Current role | Required checks |
| --- | --- | --- | --- |
| FastAPI backend | `main.py`, `api/` | HTTP API, Admin, chat endpoints | safe baseline tests, startup logs |
| Admin group controls | `api/admin/automation.py`, `core/group_controls.py`, `static/admin.html` | WhatsApp/Telegram reply ON/OFF; observation remains separate | `tests/test_group_controls.py` |
| Telegram group path | `core/telegram_bot.py`, `core/operational_memory/telegram_operational.py` | Telegram ingestion, Admin reply gate, operational replies | `tests/test_telegram_operational.py` |
| WhatsApp backend path | `api/chat.py`, `core/whatsapp_bot.py`, `core/operational_memory/whatsapp_operational.py` | WhatsApp group backend processing and operational ingest | `tests/test_whatsapp_operational.py` |
| Group reactivity and pragmatics | `core/group_reactivity.py`, `core/group_pragmatics.py` | Social/delicate autonomous trigger policy and response posture | group/pragmatic tests before behavior changes |
| Operational ingest filter | `core/operational_memory/` | Silent ingest, task/issue/decision extraction boundaries | `tests/test_operational_ingest_filter.py` |
| Admin fallback monitor | `api/admin_fallback.py`, `core/fallback_engine.py` | Reads fallback summary/raw/download data | `tests/test_admin_fallback.py` |
| Auth basics | `auth/` | Login/admin protection/rate limiting | auth tests before auth changes |

## Operational Rules

- Genesi can observe/ingest groups where present.
- Visible group replies are controlled by Admin reply settings and platform gates.
- Unknown groups default to reply OFF.
- Do not re-enable broad `group_interventions` or global greeting replies without product approval and tests.
- Do not change `WHATSAPP_CHAT_PROJECT_MAP` or `TELEGRAM_CHAT_PROJECT_MAP` as part of code cleanup.

## Safe Change Pattern

1. Create a worktree in `/tmp`.
2. Change one component boundary at a time.
3. Run the targeted test first.
4. Run the safe baseline.
5. Cherry-pick the small commit to `gold-faro-stable`.
6. Verify autodeploy and logs.

