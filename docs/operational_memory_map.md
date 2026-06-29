# Operational Memory Map

Riferimento audit: `/tmp/genesi_deep_audit_20260628_092725/`.

Questo documento descrive lo stato reale della memoria operativa senza proporre
modifiche runtime. Il principio operativo resta:

- osservazione/ingest separati dalle risposte visibili;
- mapping progetto via env/config, non da Admin UI;
- nessun invio live se il canale non e esplicitamente abilitato;
- nessuna migrazione di `memory/` o `data/` implicita.

## Confini Live

| Area | File principali | Stato | Test principali |
| --- | --- | --- | --- |
| Bridge Telegram | `core/operational_memory/telegram_operational.py` | Live ma opt-in via env e mapping | `tests/test_telegram_operational.py` |
| Bridge WhatsApp | `core/operational_memory/whatsapp_operational.py` | Live ma opt-in via env e mapping | `tests/test_whatsapp_operational.py` |
| Routing invocazioni | `invocation_router.py`, `query_engine.py` | Stabile per briefing/report/query operative | `tests/test_operational_command_interaction.py`, `tests/test_operational_query.py` |
| Ingest e stato | `chat_presence.py`, `event_store.py`, `state_engine.py`, `state_store.py` | Cuore operativo affidabile, file-backed | `tests/test_operational_memory.py`, `tests/test_operational_ingest_filter.py` |
| Lifecycle | `lifecycle_engine.py`, `workflow_engine.py`, `snapshot_delta.py` | Buona copertura, logica complessa | `tests/test_operational_lifecycle*.py`, `tests/test_operational_snapshot_delta.py` |
| Report | `daily_report.py`, `report_store.py`, `report_viewer.py` | Usabile, da tenere documentato | `tests/test_operational_report_viewer*.py`, `tests/test_report_viewer.py` |
| Media/OCR | `media_processor.py`, `image_describer.py`, `video_describer.py`, `audio_transcriber.py` | Funziona con fallback, dipendenze esterne fragili | `tests/test_operational_media_*`, `tests/test_operational_image_describer.py`, `tests/test_operational_audio_transcriber.py` |

## Flusso Telegram

1. `core/telegram_bot.py` riceve update.
2. Se il gruppo e mappato e `OPERATIONAL_MEMORY_TELEGRAM_ENABLED` e true,
   chiama `maybe_handle_operational()`.
3. Messaggi non invocati vengono ingeriti in background e il bot principale
   prosegue.
4. Invocazioni operative con reply enabled producono report/briefing.
5. Il controllo Admin gruppi resta separato: decide la reply visibile del bot
   conversazionale, non il mapping operational.

Rischio: Telegram operational reply e group Admin reply sono due controlli
diversi. Non vanno fusi senza una decisione prodotto esplicita.

## Flusso WhatsApp

1. Baileys passa prima dai gate runtime e poi dal backend.
2. Per gruppi operational mappati, `maybe_handle_whatsapp_operational()` e
   dominante: ingest silenzioso e claim del messaggio.
3. Le reply operative richiedono `WHATSAPP_OPERATIONAL_REPLY_ENABLED=true`.
4. La reply visibile di gruppo normale resta governata da env/Admin controls
   lato Baileys/backend.

Rischio: esistono due livelli di controllo WhatsApp, Baileys runtime e backend.
Il runbook Baileys documenta il confine.

## Modello Dati

| Concetto | File/modulo | Note |
| --- | --- | --- |
| Evento chat | `models.py`, `event_store.py` | Normalizzato per piattaforma e project_id |
| Stato progetto | `state_store.py`, `state_engine.py` | File-backed, testato |
| Report | `report_store.py`, `report_viewer.py` | Output operativo consultabile |
| Snapshot | `snapshot_store.py`, `snapshot_delta.py` | Usato per differenze e cambiamenti |
| Thread | `thread_engine.py`, `macro_thread_engine.py`, `thread_relation_engine.py` | Logica ricca, da tenere coperta prima di refactor |

## Media

`media_processor.py` e il punto di consolidamento per allegati. I descrittori
immagine/video/audio possono dipendere da servizi o modelli non sempre
disponibili. Il contratto attuale deve restare:

- errore gestito senza crash;
- `status` esplicito;
- testo estratto opzionale;
- descrizione opzionale;
- path confinato a directory consentite.

Prima di ogni refactor media, eseguire almeno:

```bash
python -m pytest tests/test_operational_media_processor.py tests/test_operational_image_describer.py tests/test_operational_audio_transcriber.py -q
```

## Componenti Stabili

- `invocation_router.py`: separa invocazioni operative da messaggi normali.
- `query_engine.py`: classifica intenti operativi ricorrenti.
- `chat_presence.py`: coordina ingest/reply e mantiene la pipeline leggibile.
- `state_store.py` e `report_store.py`: storage semplice e testabile.
- Bridge Telegram/WhatsApp: coperti da test, ma da mantenere sottili.

## Componenti Fragili

- `media_processor.py` e descrittori: dipendono da file, OCR, LLM o modelli.
- `thread_*`: molta logica inferenziale, rischio regressioni se refactor ampio.
- `context_binding.py`: utile, ma sensibile a euristiche e contesto implicito.
- `watcher_engine.py`: da trattare come componente separato prima di abilitarlo
  in modo proattivo.

## Componenti Demo/Lab

- `demo_runner.py`: non e parte del runtime stabile.
- Importer export WhatsApp: utile per test/import manuali, non pipeline live.
- Workflow/watcher avanzati: conservare, ma non attivare automaticamente senza
  runbook e test mirati.

## Test Coverage

Copertura buona:

- ingest filter;
- Telegram operational;
- WhatsApp operational;
- lifecycle;
- snapshot delta;
- report viewer;
- media processor con fallback.

Gap da chiudere prima di cleanup futuri:

- contratto media cross-provider leggero;
- health check config operational senza segreti;
- test end-to-end read-only del report completo con fixture piccola;
- test per separazione Admin reply vs operational reply.

## Cose Da Non Toccare Ora

- mapping `WHATSAPP_CHAT_PROJECT_MAP` e `TELEGRAM_CHAT_PROJECT_MAP`;
- runtime `/opt/genesi-baileys`;
- dati reali in `memory/` e `data/`;
- attivazione globale di watcher/autopilot/evolution;
- refactor massivo dei thread engine.

## Piano Futuro Sicuro

1. Aggiungere contract test media leggero.
2. Documentare health/config senza esporre segreti.
3. Isolare demo/lab in documentazione e test, senza spostare file.
4. Consolidare solo helper puri gia coperti.
5. Valutare registry operational cross-platform solo dopo test read-only.
