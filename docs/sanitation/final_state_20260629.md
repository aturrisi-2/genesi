<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# Final Sanitation State - 2026-06-29

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

The following is persisted from `/tmp` reports.

## Four-point Final Report

# Genesi post-sanitation 4 points final report

## 1. Stato produzione finale
- Branch: `gold-faro-stable`
- Runtime dopo patch test-only: `aa06d95`
- Production Python atteso: `/opt/genesi/venv/bin/python /opt/genesi/main.py`
- `genesi.service`: active nelle verifiche finali
- `genesi-baileys.service`: active nelle verifiche finali

## 2. Hardening provider/test
- Report: `/tmp/genesi_test_provider_hardening_report.md`
- Commit test-only promosso: `aa06d95 test(groups): harden provider calls for offline operational tests`
- File modificati: `tests/test_telegram_operational.py`, `tests/test_whatsapp_operational.py`
- Patch: monkeypatch del fallback image vision nei test operational e fail-fast se viene chiamato il provider reale.
- Test promotion verdi:
  - `test_telegram_operational`: 29 passed
  - `test_whatsapp_operational`: 99 passed
  - `test_operational_ingest_filter`: 30 passed
  - `test_group_controls`: 15 passed
  - `test_no_startup_side_effects`: 4 passed
  - py_compile: OK
  - provider leak grep: 0

## 3. Stato refined staging
- Staging precedente: `/tmp/genesi_venv_staging_refined_20260629_194213`
- Stato: `REFINED_STAGING_TESTABLE`, `DO_NOT_SWITCH`
- Non modificato in questa fase.
- Resta valido come base analitica, non come replacement production.

## 4. Heavy live-only owner review
- CSV: `/tmp/genesi_heavy_live_only_owner_review.csv`
- Report: `/tmp/genesi_heavy_live_only_owner_review.md`
- Piano: `/tmp/genesi_heavy_live_only_action_plan.md`
- Classificazioni:
  - `LEGACY_HEAVY_PROBABLE`: 18
  - `KEEP_WEB_TTS_STT`: 2
  - `KEEP_MEDIA_OCR`: 5
  - `FEATURE_FROZEN`: 2
  - `UNKNOWN_OWNER`: 3
- Nessuna rimozione proposta senza owner review. Nessuna modifica requirements.

## 5. Legacy archive candidates
- Safe CSV: `/tmp/genesi_legacy_archive_safe_candidates.csv`
- Blocked CSV: `/tmp/genesi_legacy_archive_blocked_candidates.csv`
- Manifest: `/tmp/genesi_legacy_archive_manifest.tsv`
- Backup plan: `/tmp/genesi_legacy_archive_backup_plan.md`
- Phase report: `/tmp/genesi_legacy_archive_phase_report.md`
- Backup creato solo per 5 file piccoli non critici: `/tmp/genesi_legacy_archive_backup_20260629_200035.tgz`
- Nessuna cancellazione o spostamento.
- ONNX model, heavy packages, auth/Baileys/memory/data/operational/media esclusi o bloccati.

## 6. Log/cache policy
- Policy v2: `/tmp/genesi_log_cache_policy_proposal_v2.md`
- Matrix: `/tmp/genesi_log_cache_policy_matrix.csv`
- Nessun truncate, nessun logrotate/systemd change.
- Baileys media-cache, memory/data/db/auth restano `DO_NOT_TOUCH`.

## 7. Stop gate aperti
- Non rimuovere heavy production packages.
- Non modificare `requirements.txt` repo senza fase dedicata.
- Non switchare venv.
- Non cancellare staging `/tmp` senza conferma.
- Non archiviare legacy safe senza conferma umana separata.
- Non toccare ONNX model senza owner review + backup.
- Non applicare log/cache policy senza approvazione.

## 8. Azioni future ordinate
Vedi `/tmp/genesi_post_sanitation_next_actions.csv`.

## 9. Cose da NON fare
- Non cancellare venv live.
- Non cancellare `.venv`.
- Non toccare Baileys runtime o media-cache.
- Non toccare memory/data/db/auth.
- Non cambiare env/systemd.
- Non attivare reply TAB.
- Non rimuovere heavy packages da production.

## 10. Vincoli rispettati
- Nessuna cancellazione o spostamento production.
- Nessun env/systemd/Baileys/memory/data/db.
- Nessun messaggio WhatsApp/Telegram.
- Nessun POST live.
- Nessun pip install/uninstall production.
- Nessun restart manuale.
- Unico commit/push: patch test-only autorizzata.


## Broader Sanitation Roadmap

# Genesi sanitation roadmap finale

## 1. Stato produzione
- Repo live: `/opt/genesi`
- Branch: `gold-faro-stable`
- HEAD live/origin di riferimento: `890a47d`
- Production Python: `/opt/genesi/venv/bin/python /opt/genesi/main.py`
- `genesi.service`: active durante le verifiche
- `genesi-baileys.service`: active durante le verifiche
- Dirty/untracked preesistenti da non ripulire automaticamente: `genesi_graph.json`, `.venv/`, `genesi/ai_engineer_os/logs/coding_observations_2026-03-01.json`, `static/ig_posts/`

## 2. Cleanup safe-only gia' fatto
- Backup usato: `/tmp/genesi_cleanup_safe_only_backup_20260629_185443.tgz`
- Manifest usato: `/tmp/genesi_cleanup_safe_only_manifest_20260629_185443.tsv`
- Cancellati solo file safe-only gia' backuppati/verificati.
- Nessun DUBBIO o CRITICO toccato.
- Report: `/tmp/genesi_cleanup_safe_only_delete_final_report.md`

## 3. Stato DUBBIO
- Report: `/tmp/genesi_cleanup_dubbio_order_report.md`
- DUBBIO dominato da `/opt/genesi/venv`, quindi dipendenza ambiente production live.
- Nessun esperimento fallito evidente emerso come cleanup diretto.
- Risultati principali precedenti: DIPENDENZA_AMBIENTE 315 file / circa 7.4G; CRITICO_RIVALUTATO 9 file; modello ONNX da verificare; log/cache da policy.

## 4. Stato ambiente Python
- Report: `/tmp/genesi_python_env_audit_report.md`
- Live: `/opt/genesi/venv`, Python 3.11.14, circa 9.5G, 334 package.
- `.venv`: non usato dal service, Python 3.12.3, circa 1.5G, non drop-in replacement.
- Staging base da requirements attuale: `/tmp/genesi_venv_staging_20260629_192534`, install OK ma non testabile per mancanza pytest.
- Staging refined: `/tmp/genesi_venv_staging_refined_20260629_194213`, install OK, 1.4G, 158 package, testabile ma `DO_NOT_SWITCH`.

## 5. Stato requirements
- Reconciliation report: `/tmp/genesi_requirements_reconciliation_report.md`
- Refinement report: `/tmp/genesi_requirements_refinement_report.md`
- Runtime candidate refined/v2: `/tmp/genesi_requirements_runtime_candidate_v2.txt`
- Dev/test candidate refined/v2: `/tmp/genesi_requirements_dev_test_candidate_v2.txt`
- Legacy heavy review v2: `/tmp/genesi_requirements_legacy_heavy_review_v2.txt`
- Unknown review v2: `/tmp/genesi_requirements_unknown_review_v2.txt`
- Staging refined conclusion: `REFINED_STAGING_TESTABLE`, `DO_NOT_SWITCH`.
- Stop gate: non reinserire automaticamente heavy/legacy (`torch`, `tensorflow`, `TTS`, `gruut`, `nvidia-*`, `triton`, `playwright`, `selenium`, `onnxruntime`) senza owner review.

## 6. Stato modello ONNX
- Report: `/tmp/genesi_model_onnx_owner_review.md`
- Modello: `/opt/genesi/models/leonardo-epoch=2024-step=996300.onnx`
- Dimensione: 60.6 MB
- Git tracked: true
- Riferimenti diretti al filename: non trovati.
- Classificazione: `ORPHAN_MODEL` probabile, ma `NON_TOCCARE` finche' non c'e' conferma owner, manifest e backup.

## 7. Stato log/cache
- Policy proposal: `/tmp/genesi_log_cache_policy_proposal.md`
- `/opt/genesi/genesi.log`: `LOG_DA_POLICY`; non truncare manualmente.
- `genesi/ai_engineer_os/logs/coding_observations_2026-03-01.json`: log storico/sviluppo, candidate archive solo dopo backup e owner review.
- Cache media/audio/TTS/STT/Baileys: non safe-only; richiede policy specifica.
- `/opt/genesi-baileys/media-cache/`: CRITICO, non toccare.

## 8. Stato legacy/archive
- Report: `/tmp/genesi_legacy_archive_candidates_report.md`
- CSV: `/tmp/genesi_legacy_archive_candidates.csv`
- Candidati totali: 55
- File candidati: workflow backup, log storico sviluppo, modello ONNX, lab/training scripts.
- Documentazione `docs/legacy_*`: da tenere e documentare, non archiviare.
- Lab/auth report e runner auth: classificati conservativamente `NON_TOCCARE` per parola chiave auth.

## 9. Rischi aperti
- Requirements repo non rappresenta ancora il venv live production.
- Staging refined passa test selezionati ma non e' drop-in replacement.
- Alcuni test safe attivano path provider/vision: serve mock/offline hardening.
- Heavy live-only devono avere owner feature prima di qualunque rimozione/rebuild.
- `.venv/` non usata dal service ma non va rimossa senza fase dedicata, backup e conferma.
- Modello ONNX tracciato da Git ma apparentemente orfano: richiede decisione umana.

## 10. Fasi future autorizzabili
1. Rendere completamente offline/mocked i test staging che attivano provider vision.
2. Requirements repo docs-only o PR dedicata con `requirements.runtime.candidate.txt` e `requirements.dev-test.candidate.txt`, senza switch.
3. Owner review heavy packages e modello ONNX.
4. Archive legacy dopo manifest + backup + conferma umana.
5. Policy logrotate/cache con modifica systemd/logrotate solo dopo approvazione.
6. Staging venv v3 con candidate aggiornati e test piu' estesi.
7. Switch venv solo con rollback, maintenance window e approvazione.
8. Cleanup `.venv` solo dopo prova, backup e conferma.

## 11. Stop list assoluta
Non toccare senza gate umano esplicito:
- WhatsApp, Telegram, Baileys.
- `/opt/genesi-baileys/index.js` e `/opt/genesi-baileys/media-cache/`.
- Operational Memory.
- `/opt/genesi/memory`, `/opt/genesi/data`, database, auth, mapping, reply flags.
- Env, systemd, token, whitelist.
- Gruppo TAB CEFLA / mapping/reply.

## 12. Conferma modifiche production
Durante questo mandato:
- Nessuna cancellazione DUBBIO/CRITICO.
- Nessuna modifica repo intenzionale.
- Nessuna modifica requirements repo.
- Nessun install/uninstall in production venv o `.venv`.
- Nessuno switch interpreter/service.
- Nessun commit/push/deploy/restart.
- Nessun Baileys/env/systemd/memory/data/db.
- Nessun messaggio WhatsApp/Telegram.
- Nessun POST live.
- Scritto solo in `/tmp` e creato venv staging isolato in `/tmp`.

