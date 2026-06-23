# GENESI — Main Report (quadro storico/strutturale)

> Report principale persistente. Aggiornato a ogni intervento rilevante.
> Companion operativo: `docs/GENESI_LAST_REPORT.md` (ultimo stato).

---

## 1. Branch e ambiente

- **Branch di lavoro locale:** `gold-faro-stable` (ramo stabile/produttivo).
- **Lavoro separato (NON toccare):** `gold-operational-bridge` e `operational-memory-mvp` = linea WhatsApp/Operational Memory, gira su VPS/tmux.
- Push/deploy su `gold-faro-stable` attiva auto-deploy VPS → **mai pushare senza conferma esplicita**.

## 2. Architettura risposta (stabile)

- `core/proactor.py` — orchestratore deterministico. Routing: Identity → Tool → Knowledge → Relational.
- `core/simple_chat.py` — entry point chat, chiama `proactor.handle()`.
- `core/message_pipeline.py` — pipeline memory platform-independent.
- `core/response_filter.py` — **filtro post-generazione centrale** (`filter_response`), chiamato in proactor a fine generazione (relational/knowledge/document).
- `core/telegram_group_memory.py` — `build_group_context()` costruisce il contesto di gruppo (usato sia Telegram sia WhatsApp).
- Adapter: `core/whatsapp_bot.py`, `core/telegram_bot.py`.

### Flusso risposta gruppo
```
messaggio utente (gruppo)
  → whatsapp_bot/telegram_bot
  → build_group_context()  [inietta sezioni [CONTESTO FAMIGLIA], [REGOLA FONDAMENTALE], ...]
  → message = msg + group_ctx
  → _chat → proactor.handle (relational)
  → LLM
  → filter_response()   ← choke centrale
  → send_message
```

## 3. Problema noto: prompt leakage nei gruppi

Nel gruppo WhatsApp familiare Genesi risponde molto bene, ma a volte **copia letteralmente nel testo finale** sezioni del prompt interno:
- `CONTESTO FAMIGLIA…`, `REGOLE DI INFERENZA…`, `REGOLA FONDAMENTALE…`
- `DISCUSSIONE IN CORSO…`, `RISPOSTE RECENTI…`, `FINE DISCUSSIONE`
- prefissi speaker errati (`Genesi:`), blocchi `[...]` con istruzioni interne.

**Causa:** i marcatori sono iniettati come testo `[...]` MAIUSCOLO facilmente imitabile; `filter_response` non aveva copertura per questi blocchi (solo frasi coach/meta-AI).

## 4. Soluzione (protezione multilivello)

- **L1 — prompt assembly:** guard esplicito "non copiare testo tra parentesi quadre".
- **L2 — filtro robusto:** `strip_internal_prompt_leak()` in `response_filter.py` rimuove blocchi `[...]` con keyword interne, righe-titolo MAIUSCOLE, marcatori `→ Genesi:`; preserva emote innocue.
- **L4 — fallback:** se la risposta resta contaminata/vuota → `filter_response` ritorna `""` → caller rigenera/usa fallback breve sicuro (nessun loop).
- **L3 — validazione:** `tests/test_prompt_leak_filter.py` (10 casi) + regressione narrativa esistente verde.

## 5. Stato test

- Baseline: `tests/test_narrative_coherence.py`, `tests/test_group_output_and_names.py` (verdi).
- Nuovi: `tests/test_prompt_leak_filter.py` → 10/10. Regressione gruppo/narrativa → 98/98.
- Suite completa: 709 passed / 60 failed (tutti pre-esistenti, verificati via baseline stash — zero regressioni dalla patch).

## 6. Rischi residui

- LLM può produrre leakage in forme non previste (no parentesi). Mitigazione: keyword-based + heuristica contaminazione.
- Filtro troppo aggressivo potrebbe tagliare parentesi legittime → mitigato preservando `[...]` senza keyword interne.

## 7. Convenzioni operative future

- Niente hardcoding di nomi gruppo nel filtro.
- Ogni nuova sezione di prompt con marcatore `[...]` MAIUSCOLO va aggiunta alla keyword-list del filtro.
- Aggiornare SEMPRE entrambi i report (main = struttura, last = ultimo stato).
- Nessun push/deploy senza conferma.

## 8. Decisioni fatte

- `.gitignore` hardening: esclusi `real_exports/` (PII), `genesi_gold_faro/` (clone), output generati, scratch (commit locale `e594698`).
- `docs/WORKFLOW_CLAUDE_CODE_GITHUB_VPS.md` redatto (no IP/user/path reali) e committato locale (`91ef446`).
- `docs/project_current_status.md` lasciato a `operational-memory-mvp` (non committato su gold).
