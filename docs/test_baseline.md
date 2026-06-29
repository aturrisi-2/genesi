# Genesi Safe Test Baseline

This baseline is the required minimum after cleanup changes that touch the current production core.

## Required Commands

```bash
/opt/genesi/.venv/bin/python -m pytest tests/test_group_controls.py -q
/opt/genesi/.venv/bin/python -m pytest tests/test_admin_fallback.py -q
/opt/genesi/.venv/bin/python -m pytest tests/test_telegram_operational.py -q
/opt/genesi/.venv/bin/python -m pytest tests/test_whatsapp_operational.py -q
/opt/genesi/.venv/bin/python -m pytest tests/test_operational_ingest_filter.py -q
/opt/genesi/.venv/bin/python -m py_compile \
  core/group_controls.py \
  api/admin/automation.py \
  api/admin_fallback.py \
  core/fallback_engine.py \
  core/telegram_bot.py \
  core/operational_memory/telegram_operational.py \
  core/operational_memory/whatsapp_operational.py
```

## What This Covers

| Test | Coverage |
| --- | --- |
| `tests/test_group_controls.py` | Admin WhatsApp/Telegram reply controls, default OFF behavior, atomic group controls write |
| `tests/test_admin_fallback.py` | Admin fallback summary/download tolerance for legacy records |
| `tests/test_telegram_operational.py` | Telegram operational ingest/reply/media boundaries |
| `tests/test_whatsapp_operational.py` | WhatsApp operational ingest/reply/media boundaries and backend group paths |
| `tests/test_operational_ingest_filter.py` | Filtering rules for operational memory ingestion |
| `py_compile` | Syntax/import-level sanity for core touched modules |

## Not Covered By This Baseline

- Full external integrations.
- Live Telegram/WhatsApp messages.
- Baileys live runtime behavior after manual sync.
- Real OCR/STT/TTS provider availability.
- iCloud/Google credential validity.
- Browser automation/social publishing.
- Destructive or mutating Admin POSTs against production.

## Failure Policy

- Stop on any new failure.
- Do not push to `gold-faro-stable` while the baseline is red.
- If a failure is pre-existing, document the exact evidence before proceeding.
- Do not broaden the task to fix unrelated failures without approval.

