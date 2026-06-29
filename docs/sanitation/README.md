<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# Genesi Sanitation Documentation

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

This directory preserves the final state of the Genesi sanitation work completed on 2026-06-29. It is not an operational playbook to execute automatically. It records decisions, stop gates, candidate lists, and future plans.

## Production State
- Production branch: `gold-faro-stable`
- Documented runtime HEAD: `aa06d95`
- Production process: `/opt/genesi/venv/bin/python /opt/genesi/main.py`
- `genesi.service`: active at final verification
- `genesi-baileys.service`: active at final verification

## What Was Done
- Safe-only cleanup was completed earlier with backup and manifest.
- Operational tests were hardened so Telegram/WhatsApp media tests do not call real vision providers.
- Python environments and requirements candidates were analyzed.
- Heavy live-only packages were classified for owner review.
- Legacy archive candidates were inventoried and a small backup was prepared for safe candidates only.
- Log/cache policy was proposed but not applied.

## What Was Not Done
- No production venv switch.
- No removal of heavy packages.
- No modification of `requirements.txt`.
- No Baileys runtime changes.
- No memory/data/database cleanup or migration.
- No env/systemd changes.
- No live WhatsApp/Telegram messages or live POST actions.

## Absolute Stop Gates
- Do not remove heavy packages from the production venv.
- Do not modify `requirements.txt` without a dedicated reviewed phase.
- Do not switch venvs.
- Do not delete staging `/tmp` artifacts without confirmation.
- Do not archive or move legacy safe candidates without separate confirmation.
- Do not touch the ONNX model without owner review plus manifest and backup.
- Do not apply log/cache policy without approval.
- Do not touch WhatsApp, Telegram, Baileys, Operational Memory, memory/data, env, systemd, mapping, or reply flags.

## Documents
- [Final State](final_state_20260629.md)
- [Next Actions](next_actions_20260629.md)
- [Python Environment Status](python_env_status_20260629.md)
- [Requirements Candidates](requirements_candidates_20260629.md)
- [Heavy Live-only Review](heavy_live_only_review_20260629.md)
- [Legacy Archive Plan](legacy_archive_plan_20260629.md)
- [Log/cache Policy](log_cache_policy_20260629.md)
- [ONNX Model Review](onnx_model_review_20260629.md)

## Recommended Order
1. Keep provider-hardening tests monitored.
2. Review heavy package ownership.
3. Decide ONNX model owner.
4. Review legacy archive safe candidates.
5. Approve or reject log/cache policy.
6. Only then consider further staging or cleanup phases.
