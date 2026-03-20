"""
IMPROVEMENT HEALTH MONITOR — Genesi
Monitora in autonomia tutti i sistemi di auto-miglioramento:
  - Moltbook heartbeat + consolidation
  - Lab feedback cycle
  - Training autopilot + LLM lesson curator
  - Active lessons pool
  - Global memory system (Moltbook bridge)
  - Corrections flow

Gira in background ogni CHECK_INTERVAL_S secondi.
Logga il risultato con tag strutturati → leggibili da grep/dashboard.
Espone get_report() per l'endpoint API.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from core.storage import storage
from core.log import log

logger = logging.getLogger("genesi")

# ── Intervalli di controllo ─────────────────────────────────────────────────
CHECK_INTERVAL_S           = 1800   # health check ogni 30 minuti
MOLTBOOK_HEARTBEAT_WARN_M  = 20     # warn se nessun heartbeat da N min
MOLTBOOK_HEARTBEAT_ERROR_M = 60
MOLTBOOK_CONSOLIDATE_WARN_H  = 2    # warn se nessuna consolidation da N ore
MOLTBOOK_CONSOLIDATE_ERROR_H = 8
LAB_CYCLE_WARN_H           = 12     # warn se lab cycle fermo da N ore
LAB_CYCLE_ERROR_H          = 36
AUTOPILOT_TICK_WARN_M      = 90     # warn se autopilot fermo da N min
AUTOPILOT_TICK_ERROR_M     = 180
LLM_CURATOR_WARN_H         = 8      # warn se curatore LLM fermo da N ore
LLM_CURATOR_ERROR_H        = 24
ACTIVE_LESSONS_WARN        = 5      # warn se meno di N lessons attive
ACTIVE_LESSONS_ERROR       = 0
GLOBAL_MEMORY_WARN_H       = 4      # warn se global_memory_system non aggiornato da N ore
GLOBAL_MEMORY_ERROR_H      = 24


def _now_utc() -> datetime:
    return datetime.utcnow()


def _hours_since(iso_str: str) -> float | None:
    """Ore trascorse dall'ISO timestamp. None se non parsabile."""
    if not iso_str:
        return None
    try:
        ts = datetime.fromisoformat(iso_str.replace("Z", ""))
        return (_now_utc() - ts).total_seconds() / 3600
    except Exception:
        return None


def _minutes_since(iso_str: str) -> float | None:
    h = _hours_since(iso_str)
    return h * 60 if h is not None else None


# ── Struttura di un check ───────────────────────────────────────────────────
def _check(name: str, status: str, detail: str, value: Any = None) -> dict:
    return {"name": name, "status": status, "detail": detail, "value": value}


OK      = "OK"
WARNING = "WARNING"
ERROR   = "ERROR"


class ImprovementHealthMonitor:

    # ── Check individuali ───────────────────────────────────────────────────

    async def _check_moltbook_heartbeat(self) -> dict:
        """Verifica che il heartbeat Moltbook stia girando."""
        try:
            ilog = await storage.load("moltbook:interaction_log",
                                      default={"interactions": []})
            interactions = ilog.get("interactions", [])
            state = await storage.load("moltbook:state", default={})
            beat_count = state.get("heartbeat_count", 0)

            # Trova l'ultimo timestamp dal log interazioni
            last_ts = None
            for rec in reversed(interactions[-20:]):
                ts = rec.get("timestamp")
                if ts:
                    last_ts = ts
                    break

            mins = _minutes_since(last_ts) if last_ts else None

            if mins is None:
                if beat_count == 0:
                    return _check("moltbook_heartbeat", ERROR,
                                  "Nessun heartbeat registrato", beat_count)
                return _check("moltbook_heartbeat", WARNING,
                              f"heartbeat_count={beat_count} ma nessuna interazione loggata",
                              beat_count)
            if mins > MOLTBOOK_HEARTBEAT_ERROR_M:
                return _check("moltbook_heartbeat", ERROR,
                              f"Ultima attività {mins:.0f} min fa (soglia errore: {MOLTBOOK_HEARTBEAT_ERROR_M}m)",
                              f"{mins:.0f}m ago")
            if mins > MOLTBOOK_HEARTBEAT_WARN_M:
                return _check("moltbook_heartbeat", WARNING,
                              f"Ultima attività {mins:.0f} min fa (soglia warn: {MOLTBOOK_HEARTBEAT_WARN_M}m)",
                              f"{mins:.0f}m ago")
            return _check("moltbook_heartbeat", OK,
                          f"Heartbeat #{beat_count}, ultima attività {mins:.0f} min fa",
                          f"{mins:.0f}m ago")
        except Exception as e:
            return _check("moltbook_heartbeat", ERROR, f"Eccezione: {e}", None)

    async def _check_moltbook_consolidation(self) -> dict:
        """Verifica che la consolidazione Moltbook stia producendo risultati."""
        try:
            insights_data = await storage.load("moltbook:interaction_insights", default={})
            consolidated_at = insights_data.get("consolidated_at")
            n_insights = len(insights_data.get("insights", []))
            n_tech = len(insights_data.get("technical_feedback", []))

            hours = _hours_since(consolidated_at)
            if hours is None:
                return _check("moltbook_consolidation", WARNING,
                              "Nessuna consolidazione ancora eseguita", None)
            if hours > MOLTBOOK_CONSOLIDATE_ERROR_H:
                return _check("moltbook_consolidation", ERROR,
                              f"Ultima consolidazione {hours:.1f}h fa (soglia: {MOLTBOOK_CONSOLIDATE_ERROR_H}h)",
                              f"{hours:.1f}h ago")
            if hours > MOLTBOOK_CONSOLIDATE_WARN_H:
                return _check("moltbook_consolidation", WARNING,
                              f"Ultima consolidazione {hours:.1f}h fa", f"{hours:.1f}h ago")
            return _check("moltbook_consolidation", OK,
                          f"Ultima consolidazione {hours:.1f}h fa — {n_insights} insights, {n_tech} tech_feedback",
                          {"hours_ago": round(hours, 1), "insights": n_insights, "tech_feedback": n_tech})
        except Exception as e:
            return _check("moltbook_consolidation", ERROR, f"Eccezione: {e}", None)

    async def _check_lab_cycle(self) -> dict:
        """Verifica che il lab feedback cycle elabori eventi e generi regole."""
        try:
            CYCLE_STATE_PATH = "memory/admin/lab_cycle_state.json"
            FALLBACK_LOG_PATH = "memory/admin/fallbacks.json"

            state: dict = {}
            if os.path.exists(CYCLE_STATE_PATH):
                try:
                    with open(CYCLE_STATE_PATH, encoding="utf-8") as f:
                        state = json.load(f)
                except Exception:
                    pass

            fallbacks: list = []
            if os.path.exists(FALLBACK_LOG_PATH):
                try:
                    with open(FALLBACK_LOG_PATH, encoding="utf-8") as f:
                        fallbacks = json.load(f)
                except Exception:
                    pass

            pending = sum(1 for e in fallbacks if isinstance(e, dict) and e.get("status") == "pending")
            last_run = state.get("last_run")
            rules_generated = state.get("rules_generated", 0)
            events_processed = state.get("events_processed", 0)
            hours = _hours_since(last_run)

            if hours is None:
                status = WARNING if pending < 5 else ERROR
                return _check("lab_feedback_cycle", status,
                              f"Ciclo mai eseguito — {pending} eventi pending", pending)
            if hours > LAB_CYCLE_ERROR_H:
                return _check("lab_feedback_cycle", ERROR,
                              f"Ultimo ciclo {hours:.1f}h fa, {pending} pending (soglia: {LAB_CYCLE_ERROR_H}h)",
                              {"hours_ago": round(hours, 1), "pending": pending})
            if hours > LAB_CYCLE_WARN_H and pending > 5:
                return _check("lab_feedback_cycle", WARNING,
                              f"Ciclo fermo da {hours:.1f}h con {pending} eventi in attesa",
                              {"hours_ago": round(hours, 1), "pending": pending})
            return _check("lab_feedback_cycle", OK,
                          f"Ultimo ciclo {hours:.1f}h fa — {rules_generated} regole, {pending} pending",
                          {"hours_ago": round(hours, 1), "rules": rules_generated, "pending": pending})
        except Exception as e:
            return _check("lab_feedback_cycle", ERROR, f"Eccezione: {e}", None)

    async def _check_autopilot(self) -> dict:
        """Verifica che l'autopilot di training stia girando e curando le lessons."""
        try:
            state = await storage.load("admin/autopilot_state", default={})
            if not isinstance(state, dict):
                state = {}

            last_tick = state.get("last_tick")
            last_curation = state.get("last_llm_curation")
            curation_reason = state.get("last_curation_reason", "")
            ticks = state.get("ticks_total", 0)

            tick_mins = _minutes_since(last_tick)
            curation_hours = _hours_since(last_curation)

            issues = []
            worst = OK

            if tick_mins is None:
                worst = ERROR
                issues.append("autopilot mai partito")
            elif tick_mins > AUTOPILOT_TICK_ERROR_M:
                worst = ERROR
                issues.append(f"tick fermo da {tick_mins:.0f}m")
            elif tick_mins > AUTOPILOT_TICK_WARN_M:
                worst = WARNING
                issues.append(f"tick lento: {tick_mins:.0f}m fa")

            if curation_hours is None:
                if worst != ERROR:
                    worst = WARNING
                issues.append("curatore LLM mai eseguito")
            elif curation_hours > LLM_CURATOR_ERROR_H:
                worst = ERROR
                issues.append(f"curatore LLM fermo da {curation_hours:.1f}h")
            elif curation_hours > LLM_CURATOR_WARN_H:
                if worst == OK:
                    worst = WARNING
                issues.append(f"curatore LLM: {curation_hours:.1f}h fa")

            detail_parts = [f"tick #{ticks}"]
            if tick_mins is not None:
                detail_parts.append(f"ultima esecuzione {tick_mins:.0f}m fa")
            if curation_hours is not None:
                detail_parts.append(f"LLM curator {curation_hours:.1f}h fa")
            if curation_reason:
                detail_parts.append(f"reason='{curation_reason[:60]}'")
            if issues:
                detail_parts.append(f"⚠ {', '.join(issues)}")

            return _check("training_autopilot", worst, " | ".join(detail_parts),
                          {"ticks": ticks, "tick_min_ago": round(tick_mins or 0, 1),
                           "curation_h_ago": round(curation_hours or 0, 1)})
        except Exception as e:
            return _check("training_autopilot", ERROR, f"Eccezione: {e}", None)

    async def _check_active_lessons(self) -> dict:
        """Verifica il pool di lessons attive e la distribuzione delle corrections."""
        try:
            corrections = await storage.load("admin/corrections", default=[])
            if not isinstance(corrections, list):
                corrections = []

            total = len(corrections)
            active = sum(1 for c in corrections if c.get("lesson_active"))
            pinned = sum(1 for c in corrections if c.get("lesson_pinned"))
            from_moltbook = sum(1 for c in corrections if c.get("source") == "moltbook_agent_comment")
            moltbook_active = sum(1 for c in corrections
                                  if c.get("source") == "moltbook_agent_comment"
                                  and c.get("lesson_active"))

            # Categoria più rappresentata
            from collections import Counter
            cat_counts = Counter(c.get("category", "altro") for c in corrections
                                 if c.get("lesson_active"))
            top_cat = cat_counts.most_common(1)

            if active <= ACTIVE_LESSONS_ERROR and total > 0:
                return _check("active_lessons", ERROR,
                              f"0 lessons attive su {total} corrections disponibili!", 0)
            if active < ACTIVE_LESSONS_WARN:
                return _check("active_lessons", WARNING,
                              f"Solo {active} lessons attive (soglia: {ACTIVE_LESSONS_WARN}), "
                              f"totale corrections: {total}", active)

            top_str = f" | top_cat={top_cat[0][0]}({top_cat[0][1]})" if top_cat else ""
            return _check("active_lessons", OK,
                          f"{active} attive (pinned={pinned}) su {total} — "
                          f"Moltbook: {moltbook_active}/{from_moltbook} attive{top_str}",
                          {"active": active, "pinned": pinned, "total": total,
                           "from_moltbook": from_moltbook, "moltbook_active": moltbook_active})
        except Exception as e:
            return _check("active_lessons", ERROR, f"Eccezione: {e}", None)

    async def _check_global_memory_system(self) -> dict:
        """Verifica che il bridge Moltbook → global_memory stia funzionando."""
        try:
            data = await storage.load("global_insights:moltbook_system", default={})
            if not isinstance(data, dict):
                data = {}

            last_updated = data.get("last_consolidated_at")
            n_insights = len(data.get("insights", []))
            hours = _hours_since(last_updated)

            if hours is None or n_insights == 0:
                return _check("global_memory_system", WARNING,
                              "Nessun insight Moltbook ancora nel global memory (atteso dopo prima consolidazione)",
                              0)
            if hours > GLOBAL_MEMORY_ERROR_H:
                return _check("global_memory_system", ERROR,
                              f"Global memory system non aggiornato da {hours:.1f}h (soglia: {GLOBAL_MEMORY_ERROR_H}h)",
                              {"hours_ago": round(hours, 1), "insights": n_insights})
            if hours > GLOBAL_MEMORY_WARN_H:
                return _check("global_memory_system", WARNING,
                              f"Global memory system aggiornato {hours:.1f}h fa — {n_insights} insights",
                              {"hours_ago": round(hours, 1), "insights": n_insights})
            return _check("global_memory_system", OK,
                          f"{n_insights} insights Moltbook nel contesto — aggiornato {hours:.1f}h fa",
                          {"hours_ago": round(hours, 1), "insights": n_insights})
        except Exception as e:
            return _check("global_memory_system", ERROR, f"Eccezione: {e}", None)

    async def _check_corrections_flow(self) -> dict:
        """Verifica che le corrections continuino ad arrivare (sistema aperto)."""
        try:
            corrections = await storage.load("admin/corrections", default=[])
            if not isinstance(corrections, list):
                corrections = []

            now = _now_utc()
            recent_24h = 0
            recent_7d = 0
            for c in corrections:
                ts = c.get("timestamp")
                if not ts:
                    continue
                try:
                    age_h = (now - datetime.fromisoformat(ts)).total_seconds() / 3600
                    if age_h <= 24:
                        recent_24h += 1
                    if age_h <= 168:
                        recent_7d += 1
                except Exception:
                    pass

            if recent_7d == 0 and len(corrections) > 0:
                return _check("corrections_flow", WARNING,
                              "Nessuna nuova correction negli ultimi 7 giorni — sistema potrebbe essere fermo",
                              {"24h": recent_24h, "7d": recent_7d})
            return _check("corrections_flow", OK,
                          f"Corrections: {recent_24h} nelle ultime 24h, {recent_7d} negli ultimi 7gg — "
                          f"totale: {len(corrections)}",
                          {"24h": recent_24h, "7d": recent_7d, "total": len(corrections)})
        except Exception as e:
            return _check("corrections_flow", ERROR, f"Eccezione: {e}", None)

    # ── Report completo ─────────────────────────────────────────────────────

    async def get_report(self) -> dict:
        """Esegue tutti i check e ritorna il report completo."""
        checks = [
            await self._check_moltbook_heartbeat(),
            await self._check_moltbook_consolidation(),
            await self._check_lab_cycle(),
            await self._check_autopilot(),
            await self._check_active_lessons(),
            await self._check_global_memory_system(),
            await self._check_corrections_flow(),
        ]

        counts = {OK: 0, WARNING: 0, ERROR: 0}
        for c in checks:
            counts[c["status"]] += 1

        # Punteggio: OK=100%, ogni WARNING -10%, ogni ERROR -20%
        score = max(0.0, 100.0 - counts[WARNING] * 10 - counts[ERROR] * 20)

        overall = OK
        if counts[ERROR] > 0:
            overall = ERROR
        elif counts[WARNING] > 0:
            overall = WARNING

        return {
            "overall": overall,
            "score": round(score, 1),
            "generated_at": _now_utc().isoformat(),
            "checks": checks,
            "summary": counts,
        }

    # ── Log strutturato ─────────────────────────────────────────────────────

    async def log_report(self) -> dict:
        """Esegue get_report() e logga il risultato in genesi.log."""
        report = await self.get_report()
        overall = report["overall"]
        score = report["score"]
        summary = report["summary"]

        # Log aggregato
        log_tag = (
            "IMPROVEMENT_HEALTH_OK"      if overall == OK else
            "IMPROVEMENT_HEALTH_WARNING" if overall == WARNING else
            "IMPROVEMENT_HEALTH_ERROR"
        )
        log(log_tag,
            score=score,
            ok=summary[OK],
            warnings=summary[WARNING],
            errors=summary[ERROR])

        # Log dettaglio per ogni check non-OK
        for c in report["checks"]:
            if c["status"] != OK:
                log("IMPROVEMENT_HEALTH_DETAIL",
                    component=c["name"],
                    status=c["status"],
                    reason=c["detail"][:120])

        return report

    # ── Background loop ─────────────────────────────────────────────────────

    async def run_background_loop(self):
        """Loop background: health check ogni CHECK_INTERVAL_S secondi."""
        import asyncio
        # Attesa iniziale per non sovraccaricare il boot
        await asyncio.sleep(120)
        logger.info("IMPROVEMENT_HEALTH_MONITOR_STARTED interval=%ds", CHECK_INTERVAL_S)
        while True:
            try:
                await self.log_report()
            except Exception as e:
                logger.warning("IMPROVEMENT_HEALTH_MONITOR_ERROR err=%s", e)
            await asyncio.sleep(CHECK_INTERVAL_S)


improvement_health = ImprovementHealthMonitor()
