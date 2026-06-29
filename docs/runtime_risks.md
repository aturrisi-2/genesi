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

