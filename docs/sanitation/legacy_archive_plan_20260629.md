<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# Legacy Archive Plan - 2026-06-29

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

# Genesi legacy archive phase report

## Sintesi
- Safe archive candidates: 5
- Blocked candidates: 50
- Manifest: `/tmp/genesi_legacy_archive_manifest.tsv`
- Backup: `/tmp/genesi_legacy_archive_backup_20260629_200035.tgz`

## Safe candidates
- `/opt/genesi/genesi/ai_engineer_os/logs/coding_observations_2026-03-01.json` size=936
- `/opt/genesi/lab/massive_training_runner.py` size=15090
- `/opt/genesi/scripts/training_cycle.py` size=21900
- `/opt/genesi/scripts/sensory_skills_test.py` size=5122
- `/opt/genesi/scripts/training_marathon.py` size=128417

## Blocked rationale
- Heavy packages are not backed up from production venv.
- ONNX model is blocked pending owner review.
- Auth/Baileys/Operational/media/memory/data paths are blocked.
- Docs/workflow utility are kept, not archived.

## Constraints
- No delete.
- No move.
- No production modification.


---

# Genesi legacy archive backup plan

## Safe candidates
- Count: 5
- Manifest: `/tmp/genesi_legacy_archive_manifest.tsv`
- Backup created: `/tmp/genesi_legacy_archive_backup_20260629_200035.tgz` (5 entries)

## Blocked candidates
- Count: 50
- CSV: `/tmp/genesi_legacy_archive_blocked_candidates.csv`

## Rules
- No deletion.
- No move.
- No venv/heavy package backup.
- No model ONNX backup without owner gate.
- No auth/Baileys/memory/data/operational/media paths.

## Future archive procedure
1. Human review safe CSV.
2. Confirm archive target.
3. Verify backup and manifest.
4. Only then move/archive files in a separate approved phase.


## Important
The backup referenced here was created in `/tmp` only for reversibility. It does not authorize deletion or movement of production files.
