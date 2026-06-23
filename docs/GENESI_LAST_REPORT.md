# GENESI — Last Report (ultimo stato operativo)

> Aggiornato a ogni intervento. Companion strutturale: `docs/GENESI_MAIN_REPORT.md`.

---

## Attività corrente

**Timestamp:** 2026-06-23
**Branch:** `gold-faro-stable`
**HEAD:** `91ef446`
**Obiettivo:** anti prompt-leakage nelle risposte di gruppo WhatsApp/Telegram.

## Stato git (pre-patch)
```
?? docs/project_current_status.md   (lasciato a operational-memory-mvp)
```
Ahead 2 vs origin (commit `.gitignore` + workflow), nessun push.

## Fase: ANALISI + PIANO + IMPLEMENTAZIONE (completata, no commit)

File analizzati:
- `core/response_filter.py` — filtro centrale, nessuna copertura marcatori interni.
- `core/telegram_group_memory.py:build_group_context()` — origine marcatori `[CONTESTO FAMIGLIA]`, `[REGOLA FONDAMENTALE]`, `[DISCUSSIONE IN CORSO]`, `[RISPOSTE RECENTI]`, ecc.
- `core/whatsapp_bot.py:1283-1363` — assembly `message + group_ctx`, invio reply.
- `core/proactor.py` — `filter_response` chiamato a 3919/4553/4623.

## File modificati (patch minima additiva)
1. `core/response_filter.py` (+133) — nuova `strip_internal_prompt_leak()` + hook STEP 0 in `filter_response` (L2 + L4 fallback via return "").
2. `core/telegram_group_memory.py` (+7) — guard L1: riga "non copiare testo tra parentesi quadre".
3. `tests/test_prompt_leak_filter.py` (nuovo) — 10 casi.
4. `docs/GENESI_MAIN_REPORT.md` + questo report.

## Diff sintetico
```
 core/response_filter.py       | 133 +++++  (strip_internal_prompt_leak + hook)
 core/telegram_group_memory.py |   7 +++   (guard anti-leak)
```

## Test eseguiti
- `tests/test_prompt_leak_filter.py` → **10 passed**.
- `tests/test_narrative_coherence.py tests/test_group_output_and_names.py tests/test_group_wrapper_extraction.py` → **98 passed**.
- Suite completa: `709 passed, 60 failed, 1 skipped` (esclusa `deep_stress_test.py`: collection error pre-esistente `ModuleNotFoundError: db`).

## Risultato
- **Zero regressioni dalla patch.** I fallimenti sospetti su moduli toccati (`test_affective_event_decay`, `test_face_recognition_hardening::test_speaker_name_propagated`, `test_memory_routing::test_greeting_still_works`) falliscono **identici anche senza patch** (verificato via `git stash` dei 2 file → baseline: stessi 4 fail).
- I 60 fail sono pre-esistenti: Unicode cp1252 su Windows (emoji nei test) + lista nota in CLAUDE.md (icloud/face/neural_brain/reminder/emoji/meta_governance/evolution/watchdog/success_rate).

## Cosa resta da fare
- Attendere conferma utente per commit dei file: `core/response_filter.py`, `core/telegram_group_memory.py`, `tests/test_prompt_leak_filter.py`, `docs/GENESI_MAIN_REPORT.md`, `docs/GENESI_LAST_REPORT.md`.
- NON committare: `docs/project_current_status.md` (va su operational-memory-mvp), runtime artifacts.

## Push / Deploy
- **NON eseguiti.** Nessun push, nessun deploy, VPS intatto.
