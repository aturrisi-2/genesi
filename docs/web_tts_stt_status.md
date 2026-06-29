# Web TTS/STT Status

Aggiornato: 2026-06-29.

Questo documento classifica TTS e STT come feature dell'app Web. Non sono parte
dei gruppi WhatsApp/Telegram, non passano da Baileys e non devono produrre audio
automatico nei gruppi.

## Decisione

| Componente | Decisione | Motivo |
| --- | --- | --- |
| Web TTS `POST /api/tts/` | Tenere Web feature-gated | Frontend e backend sono coerenti, protetti da JWT e hanno provider multipli. Uso recente non confermato dai log. |
| Web STT `POST /api/stt/` | Tenere Web feature-gated | Frontend e backend sono coerenti, protetti da JWT e hanno fallback JSON sugli errori. Uso recente non confermato dai log. |
| Audio analysis media/gruppi | Tenere separato | E un percorso diverso (`AUDIO_ANALYSIS_*`) usato dalla pipeline media, non TTS/STT Web. |
| Cache/audio storici | Congelare | Non cancellare senza inventory e piano retention. |
| `tts/tts_api_legacy.py` | Spostare in legacy futuro | Non e montato da `main.py` e non e il path Web attivo. |

## Percorso TTS Web

- Frontend: `static/app.v2.js`
- Fetch: `POST /api/tts/`
- Payload: JSON `{ "text": "..." }`
- Auth: `Authorization: Bearer ...` via `authHeaders()`
- Backend: `tts/tts_api.py`
- Mount: `main.py` include `tts_router` con prefix `/api`
- Provider: `core/tts_provider.py`
- Config: `config/tts_config.json`

Il provider preferito e OpenAI TTS con fallback Edge TTS e Piper. Piper dipende
da binario e modelli host configurati con `PIPER_*`.

## Percorso STT Web

- Frontend: `static/app.v2.js`
- Registrazione: `MediaRecorder` o fallback WebAudio
- Fetch: `POST /api/stt/`
- Payload: `multipart/form-data`, campo `audio`
- Auth: `Authorization: Bearer ...` via `authHeadersRaw()`
- Backend: `api/stt.py`
- Mount: `main.py` include `stt_router` con prefix `/api`

Il default e OpenAI Whisper `whisper-1`. Se `STT_LOCAL=true`, il backend prova
`faster-whisper` locale prima del fallback remoto.

## Rischi

- TTS/STT remoti dipendono da rete, chiavi e quota.
- STT remoto invia audio a provider esterno.
- `GET /api/tts/info` oggi espone informazioni sintetiche sul provider senza
  generare audio; valutarne la protezione in una fase dedicata.
- Cache audio storiche in `tts_cache/`, `data/tts/`, `data/tts_cache/`,
  `voice_tests/`, `voice_gold/` e `static/voice_test/` non hanno retention
  documentata.
- Mancano test endpoint Web TTS/STT con provider mockati e senza chiamate
  esterne.

## Cose da non fare senza approvazione

- Non collegare TTS/STT a WhatsApp, Telegram o Baileys.
- Non inviare audio nei gruppi.
- Non cancellare cache/audio storici senza inventory e backup.
- Non attivare `STT_LOCAL` o cambiare provider/env senza test dedicati.
- Non chiamare provider esterni nei test.

## Test da aggiungere prima di modifiche future

- TTS endpoint con provider mockato, auth 401, media type e fallback.
- STT endpoint con `transcribe_audio` mockato, auth 401, form field `audio`,
  stati `empty`/`error`.
- Test statico che confermi che TTS/STT Web non sono importati o chiamati dai
  path WhatsApp/Telegram/Baileys.
