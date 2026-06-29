# Audio Cache Inventory

Aggiornato: 2026-06-29.

Questo documento registra l'inventario read-only dei file audio/cache storici
TTS/STT/Web. Non autorizza cancellazioni: ogni cleanup futuro richiede backup,
manifest e approvazione esplicita.

Report completo temporaneo:

- `/tmp/genesi_audio_cache_cleanup_audit.md`
- `/tmp/genesi_audio_cache_inventory.md`
- `/tmp/genesi_audio_cache_inventory_raw.txt`
- `/tmp/genesi_audio_cache_references.txt`
- `/tmp/genesi_audio_cache_logs_30d.txt`

## Sintesi

Il pattern di audit ha trovato 477 file per circa 37.9 MB. Il totale include
anche `venv/`, perche il comando escludeva `.venv` ma non la vecchia directory
`venv`.

| Categoria | Count | Size | Decisione |
| --- | ---: | ---: | --- |
| Dipendenze in `venv/` | 319 | 9.5 MB | Tenere, non cleanup applicativo |
| Cache TTS probabile | 73 | 20.4 MB | Candidato cleanup dopo backup |
| Demo/manual voice | 15 | 2.5 MB | Candidato archive/legacy dopo backup |
| Backup snapshot | 14 | 2.3 MB | Tenere per policy backup separata |
| Output TTS runtime storico | 7 | 1.4 MB | Tenere per ora |
| Static demo | 6 | 977 KB | Candidato archive/legacy dopo backup |
| Audio sconosciuto | 6 | 452 KB | Non toccare |

## Directory Rilevanti

- `tts_cache/`: cache TTS storica, voce piu pesante fuori dalle dipendenze.
- `data/tts_cache/`: cache/output intermedi TTS storici.
- `data/tts/`: output TTS storici, possibile contenuto utente.
- `static/voice_test/`: demo statiche servibili dal frontend.
- `voice_tests/`: campioni manuali voce.
- `voice_gold/`: golden/manual audio storici.
- `backups/.../data/tts*`: copie dentro backup storico.
- `memory/v1_media`: perimetro media/memoria, non cleanup TTS immediato.

## Non Toccare Ora

- `venv/`: dipendenze e asset di libreria.
- `backups/`: backup storici.
- `data/tts/`: possibili output utente/runtime.
- `memory/v1_media`: memoria/media.
- `static/input_audio.webm`: static audio sconosciuto.
- Qualsiasi file root tipo `test_direct.wav`, `test_coqui.wav`,
  `test_xtts.wav`, `:USERPROFILEDesktoptest_diego.mp3` senza verifica manuale.

## Candidati Futuri

Solo dopo backup e approvazione:

- `tts_cache/tts_*.wav`
- `tts_cache/tts_final_*.wav`
- `data/tts_cache/tts_*`
- `static/voice_test/*.mp3`
- `voice_tests/*.wav`
- `voice_gold/*.wav`

## Evidenza Log

Nei log filtrati degli ultimi 30 giorni non sono emersi `POST /api/tts/` o
`POST /api/stt/`. Il segnale TTS esplicito recente e il solo smoke GET:

- `GET /api/tts/info` 200
- `TTS_PROVIDER_LOADED provider=openai`

Quindi TTS/STT Web restano feature-gated e non risultano usati attivamente con
provider reali dai log osservati.

## Piano Cleanup Sicuro

1. Creare backup tar timestampato dei candidati.
2. Generare manifest con path, size, mtime e `sha256sum`.
3. Verificare riferimenti esatti nel codice e nei log.
4. Spostare in archive non servita, mai cancellare subito.
5. Eseguire baseline e test Web TTS/STT mockati.
6. Monitorare runtime per 24-48 ore.
7. Cancellare definitivamente solo con approvazione esplicita.

## Vincoli

- Nessuna cancellazione durante l'audit.
- Nessuno spostamento durante l'audit.
- Nessun audio generato.
- Nessun upload.
- Nessun POST live.
- Nessuna modifica a env, Baileys, memory o database reali.

