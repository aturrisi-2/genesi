<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# Python Environment Status - 2026-06-29

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

## Production Environment
- Active interpreter: `/opt/genesi/venv/bin/python`
- Active process: `/opt/genesi/venv/bin/python /opt/genesi/main.py`
- Live venv is production and must not be modified file-by-file.

## Non-production / Staging
- `/opt/genesi/.venv`: observed as not used by the service and not a drop-in replacement. Do not delete without a dedicated backup and approval phase.
- `/tmp/genesi_venv_staging_20260629_192534`: first staging from current `requirements.txt`, install OK but not testable because `pytest` was absent.
- `/tmp/genesi_venv_staging_refined_20260629_194213`: refined staging, install OK, testable, `DO_NOT_SWITCH`.

## Key Decision
The refined staging is useful for analysis, but it is not a production replacement. Heavy live-only packages and owner decisions remain open.

## Stop Gates
- No pip install/uninstall in `/opt/genesi/venv` or `/opt/genesi/.venv`.
- No service switch.
- No deletion of staging or `.venv` without explicit confirmation.
