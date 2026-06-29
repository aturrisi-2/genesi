<!-- DOCUMENTATION ONLY -->
<!-- DO NOT APPLY WITHOUT HUMAN APPROVAL -->

# Log/cache Policy Proposal - 2026-06-29

**DOCUMENTATION ONLY. DO NOT APPLY WITHOUT HUMAN APPROVAL.**

# Genesi log/cache policy proposal v2

## Principio
Questa e' una proposta non applicata. Nessun log e' stato troncato, nessuna cache cancellata, nessun systemd/logrotate modificato.

## Matrice
Vedi `/tmp/genesi_log_cache_policy_matrix.csv`.

## Policy per categoria

### `ROTATE_WITH_LOGROTATE_FUTURE`
Usare per log runtime come `/opt/genesi/genesi.log`. Procedura futura: configurare logrotate con retention esplicita, compressione e post-check dei servizi. Non usare truncation manuale.

### `ARCHIVE_AFTER_BACKUP`
Usare per log storici o report audit non runtime. Procedura futura: manifest sha256, tar backup, verifica `tar -tzf`, poi eventuale archive/spostamento approvato.

### `TTL_CACHE_FUTURE`
Usare per cache tool/test e cache Web TTS/STT solo dopo privacy review. La policy deve dichiarare TTL, estensioni ammesse, path ammessi e denylist critica.

### `DO_NOT_TOUCH`
Usare per Baileys media-cache, memory/data persistenti, Operational Memory, media utente, database, auth. Nessuna cancellazione manuale.

### `TMP_STAGING_CAN_DELETE_AFTER_CONFIRMATION`
Gli staging venv in `/tmp` sono tecnicamente rimovibili, ma solo dopo conferma esplicita e dopo aver salvato report/freeze utili. Non cancellati in questa fase.

### `MANUAL_REVIEW_REQUIRED`
Usare per asset/demo/cache ambigui: serve owner feature prima di backup/archive/cleanup.

## Comandi futuri suggeriti ma NON eseguiti
```bash
# esempio backup report/cache approvati
tar -czf /tmp/genesi_logs_cache_backup_YYYYMMDD_HHMMSS.tgz --files-from /tmp/approved_paths.txt

# esempio verifica backup
tar -tzf /tmp/genesi_logs_cache_backup_YYYYMMDD_HHMMSS.tgz >/tmp/backup_listing.txt
```

## Stop list
- `/opt/genesi-baileys/media-cache/`: non toccare.
- `/opt/genesi/memory/`, `/opt/genesi/data/`: non toccare.
- Database/auth/env/systemd/mapping/reply: non toccare.
- Media/audio utente: non cancellare senza privacy/owner review.

## Vincoli rispettati
- No truncation.
- No delete.
- No logrotate/systemd change.
- No Baileys/memory/data/env.


## Important
No logrotate, truncation, cache cleanup, systemd change, or Baileys media-cache action has been applied.
