"""
LAB FEEDBACK CYCLE — Converte fallback reali e suggerimenti admin in miglioramenti al system prompt.

Ciclo automatico:
1. Si attiva quando ci sono >=MIN_EVENTS eventi non processati in memory/admin/fallbacks.json
2. Legge fallback events + admin suggestions
3. Chiama gpt-4o-mini per generare regole specifiche di miglioramento
4. Inietta le regole nel system_prompt in lab/global_prompt.json
5. Marca gli eventi come "resolved" e le suggestion come "processed"
6. Salva log del ciclo in memory/admin/lab_cycle_state.json

Fail-silent: qualsiasi errore non interrompe il flusso principale.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, List

from core.log import log

logger = logging.getLogger("genesi")

# 🚨 DISABLED TO PREVENT CREDIT DRAIN
LAB_FEEDBACK_CYCLE_DISABLED = True  # SET TO FALSE TO RE-ENABLE

FALLBACK_LOG_PATH = "memory/admin/fallbacks.json"
SUGGESTIONS_PATH = "memory/admin/suggestions.json"
GLOBAL_PROMPT_PATH = "lab/global_prompt.json"
CYCLE_STATE_PATH = "memory/admin/lab_cycle_state.json"

MIN_EVENTS_TO_TRIGGER = 5    # Minimo eventi pending per avviare il ciclo automatico
MIN_HOURS_BETWEEN_CYCLES = 6  # Ore minime tra cicli successivi

_ANALYSIS_PROMPT = """\
Sei un tecnico AI che analizza problemi di un assistente personale chiamato Genesi.
Hai ricevuto log di fallback (situazioni dove Genesi ha risposto male o ha dato errori) \
e suggerimenti dell'admin.
Produci SOLO un JSON nel formato: {"rules": ["regola1", "regola2", ...]}
con al massimo 6 regole SPECIFICHE E BREVI in italiano.
Ogni regola deve iniziare con "Quando...", "Non...", "Evita...", "Sempre..." o "Se...".
Le regole devono prevenire i fallback specifici che vedi nei log.
NON inventare regole generiche. Usa solo ciò che emerge chiaramente dai problemi registrati.
Se non ci sono problemi concreti, restituisci {"rules": []}.\
"""


class LabFeedbackCycle:
    """
    Servizio che converte fallback reali e suggerimenti admin in regole
    specifiche aggiunte al system prompt di Genesi (lab/global_prompt.json).
    """

    def __init__(self):
        self._running = False

    # ── Helpers I/O ──────────────────────────────────────────────────────────

    def _load_json(self, path: str, default: Any) -> Any:
        if not os.path.exists(path):
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def _save_json(self, path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── Trigger logic ─────────────────────────────────────────────────────────

    def _count_pending_events(self) -> int:
        _NOISE_TYPES = {"moltbook_social", "moltbook_technical_feedback", "GRUPPO_FAMIGLIA"}
        events = self._load_json(FALLBACK_LOG_PATH, [])
        return sum(
            1 for e in events
            if e.get("status") == "pending"
            and e.get("fallback_type", "") not in _NOISE_TYPES
        )

    def _should_run(self) -> bool:
        """Verifica se il ciclo deve essere avviato (soglia eventi + intervallo minimo)."""
        state = self._load_json(CYCLE_STATE_PATH, {})
        last_run = state.get("last_run")
        if last_run:
            try:
                elapsed = (datetime.utcnow() - datetime.fromisoformat(last_run)).total_seconds()
                if elapsed < MIN_HOURS_BETWEEN_CYCLES * 3600:
                    return False
            except Exception:
                pass
        return self._count_pending_events() >= MIN_EVENTS_TO_TRIGGER

    def trigger_if_needed(self) -> None:
        """
        Chiamato da FallbackEngine dopo ogni log_event.
        Avvia il ciclo in background se la soglia è raggiunta.
        """
        # 🚨 DISABLED TO PREVENT CREDIT DRAIN
        if LAB_FEEDBACK_CYCLE_DISABLED:
            return
        if self._running:
            return
        if self._should_run():
            try:
                asyncio.create_task(self.run())
            except RuntimeError:
                pass  # Nessun event loop attivo (es. contesto sync)

    # ── Main cycle ────────────────────────────────────────────────────────────

    async def run(self, force: bool = False) -> dict:
        """
        Esegue il ciclo feedback → analisi LLM → aggiornamento prompt.

        Args:
            force: Se True, ignora il controllo di soglia/intervallo.

        Returns:
            dict con i risultati del ciclo.
        """
        if self._running and not force:
            return {"status": "already_running"}
        self._running = True
        try:
            return await self._do_cycle()
        except Exception as e:
            logger.error("LAB_FEEDBACK_CYCLE_ERROR: %s", e)
            return {"status": "error", "error": str(e)}
        finally:
            self._running = False

    async def _do_cycle(self) -> dict:
        from core.llm_service import llm_service  # import locale per evitare circular

        # 1. Carica dati
        events: List[dict] = self._load_json(FALLBACK_LOG_PATH, [])
        suggestions: List[dict] = self._load_json(SUGGESTIONS_PATH, [])

        # Filtra eventi rilevanti: esclude Moltbook (social posts/feedback AI) e
        # GRUPPO_FAMIGLIA (contesto grup, non errori). Mantiene solo errori reali e
        # finding da audit.
        _NOISE_TYPES = {"moltbook_social", "moltbook_technical_feedback", "GRUPPO_FAMIGLIA"}
        pending_events = [
            e for e in events
            if e.get("status") == "pending"
            and e.get("fallback_type", "") not in _NOISE_TYPES
        ]
        pending_suggestions = [s for s in suggestions if s.get("status") == "pending"]

        if not pending_events and not pending_suggestions:
            return {"status": "nothing_to_process"}

        # 2. Costruisce testo di analisi
        lines = ["=== FALLBACK EVENTS ==="]
        for ev in pending_events[:30]:  # max 30 eventi per non superare context window
            lines.append(
                f"- Tipo: {ev.get('fallback_type', '?')} | "
                f"Messaggio utente: {str(ev.get('user_message', ''))[:150]} | "
                f"Risposta errata data: {str(ev.get('response_given', ''))[:100]} | "
                f"Soluzione suggerita LLM: {ev.get('possible_solution', 'N/A')}"
            )

        if pending_suggestions:
            lines.append("\n=== SUGGERIMENTI ADMIN ===")
            for s in pending_suggestions:
                lines.append(f"- [{s.get('category', '?')}] {s.get('content', '')}")

        analysis_text = "\n".join(lines)

        # 3. Chiama LLM per generare regole
        # Usa _call_model direttamente per evitare che _call_with_protection
        # sostituisca _ANALYSIS_PROMPT con il system prompt adattivo di Genesi
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini",
            _ANALYSIS_PROMPT,
            analysis_text,
            user_id="admin-lab-cycle",
            route="admin",
        )

        if not raw:
            logger.warning("LAB_FEEDBACK_CYCLE: LLM returned empty response")
            return {"status": "llm_empty"}

        # 4. Parsing rules
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
            clean = clean.strip()

        try:
            parsed = json.loads(clean)
            rules: List[str] = parsed.get("rules", [])
        except Exception as e:
            logger.error("LAB_FEEDBACK_CYCLE_PARSE_ERROR: %s — raw: %s", e, clean[:300])
            return {"status": "parse_error", "error": str(e)}

        rules = [str(r).strip() for r in rules if str(r).strip()][:6]

        # 5. Aggiorna lab/global_prompt.json
        current_data = self._load_json(GLOBAL_PROMPT_PATH, {})
        base_prompt = current_data.get("system_prompt") or current_data.get("base_prompt", "")

        # Rimuovi sezione [REGOLE APPRESE] precedente se esiste
        _MARKER = "\n\n[REGOLE APPRESE DALL'ESPERIENZA]\n"
        if _MARKER in base_prompt:
            base_prompt = base_prompt.split(_MARKER)[0]

        if rules:
            rules_block = "\n".join(f"- {r}" for r in rules)
            updated_prompt = base_prompt + _MARKER + rules_block
        else:
            updated_prompt = base_prompt  # Nessuna nuova regola

        current_data["system_prompt"] = updated_prompt
        current_data["feedback_rules"] = rules
        current_data["feedback_cycle_date"] = datetime.utcnow().isoformat()
        current_data["feedback_events_processed"] = len(pending_events)
        current_data["feedback_suggestions_processed"] = len(pending_suggestions)

        Path(GLOBAL_PROMPT_PATH).parent.mkdir(parents=True, exist_ok=True)
        self._save_json(GLOBAL_PROMPT_PATH, current_data)

        # 6. Marca eventi come "resolved"
        for ev in events:
            if ev.get("status") == "pending":
                ev["status"] = "resolved"
        self._save_json(FALLBACK_LOG_PATH, events)

        # 7. Marca suggerimenti come "processed"
        for s in suggestions:
            if s.get("status") == "pending":
                s["status"] = "processed"
        self._save_json(SUGGESTIONS_PATH, suggestions)

        # 8. Salva stato ciclo
        cycle_result = {
            "last_run": datetime.utcnow().isoformat(),
            "events_processed": len(pending_events),
            "suggestions_processed": len(pending_suggestions),
            "rules_generated": len(rules),
            "rules": rules,
            "status": "success",
        }
        self._save_json(CYCLE_STATE_PATH, cycle_result)

        log(
            "LAB_FEEDBACK_CYCLE_DONE",
            events=len(pending_events),
            suggestions=len(pending_suggestions),
            rules=len(rules),
        )
        logger.info(
            "LAB_FEEDBACK_CYCLE_DONE: %d events, %d suggestions → %d rules",
            len(pending_events),
            len(pending_suggestions),
            len(rules),
        )

        return cycle_result

    def record_observation(self, category: str, observation: str, source: str = "") -> None:
        """
        Aggiunge un'osservazione esterna (es. da Moltbook) come evento pending
        nel ciclo feedback, poi triggera il ciclo se la soglia è raggiunta.
        """
        events = self._load_json(FALLBACK_LOG_PATH, [])
        if not isinstance(events, list):
            events = []
        events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "fallback_type": category,
            "user_message": f"[{source}]" if source else "[external]",
            "response_given": "",
            "possible_solution": observation,
            "status": "pending",
        })
        self._save_json(FALLBACK_LOG_PATH, events)
        self.trigger_if_needed()

    def get_status(self) -> dict:
        """Restituisce lo stato dell'ultimo ciclo eseguito."""
        state = self._load_json(CYCLE_STATE_PATH, {})
        pending = self._count_pending_events()
        state["pending_events"] = pending
        state["min_events_to_trigger"] = MIN_EVENTS_TO_TRIGGER
        state["is_running"] = self._running
        return state


# Istanza globale
lab_feedback_cycle = LabFeedbackCycle()
