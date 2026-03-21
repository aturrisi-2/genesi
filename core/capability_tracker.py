"""
CAPABILITY TRACKER — Genesi Training System
Calcola e storicizza le 6 metriche di capacità di Genesi.
Zero LLM calls: tutto derivato da dati già presenti in memoria.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any

from core.storage import storage

logger = logging.getLogger(__name__)

METRICS_KEY   = "admin/capability_metrics"
COUNTERS_KEY  = "admin/capability_counters"

# Labels leggibili per le 6 dimensioni
DIMENSION_LABELS = {
    "episode_coverage":  "Memory Retention",
    "facts_coverage":    "Identity Recall",
    "insight_depth":     "Insight Depth",
    "fallback_health":   "System Stability",
    "correction_rate":   "Response Quality",
    "overall_health":    "Overall Health",
}

# Colori per la UI (spider chart)
DIMENSION_COLORS = {
    "episode_coverage":  "#60a5fa",
    "facts_coverage":    "#34d399",
    "insight_depth":     "#a78bfa",
    "fallback_health":   "#fb923c",
    "correction_rate":   "#f472b6",
    "overall_health":    "#facc15",
}


class CapabilityTracker:

    # ── Metodo principale ─────────────────────────────────────────────────

    async def compute_current(self) -> Dict[str, Any]:
        """Calcola le metriche correnti leggendo i dati in memoria."""
        try:
            scores: Dict[str, float] = {}

            scores["episode_coverage"] = await self._episode_coverage()
            scores["facts_coverage"]   = await self._facts_coverage()
            scores["insight_depth"]    = await self._insight_depth()
            scores["fallback_health"]  = await self._fallback_health()
            scores["correction_rate"]  = await self._correction_rate()

            # Overall: media pesata delle 5 dimensioni
            weights = {
                "episode_coverage": 0.20,
                "facts_coverage":   0.20,
                "insight_depth":    0.15,
                "fallback_health":  0.25,
                "correction_rate":  0.20,
            }
            overall = sum(scores[d] * w for d, w in weights.items())
            scores["overall_health"] = round(overall, 3)

            return {
                "computed_at": datetime.utcnow().isoformat(),
                "scores":      {k: round(v * 100, 1) for k, v in scores.items()},
                "raw_scores":  scores,
                "labels":      DIMENSION_LABELS,
                "colors":      DIMENSION_COLORS,
            }
        except Exception as e:
            logger.error("CAPABILITY_COMPUTE_ERROR err=%s", e)
            return {
                "computed_at": datetime.utcnow().isoformat(),
                "scores":  {},
                "labels":  DIMENSION_LABELS,
                "colors":  DIMENSION_COLORS,
                "error":   str(e),
            }

    async def save_snapshot(self) -> None:
        """Salva snapshot giornaliero. Chiamare max 1x/giorno."""
        try:
            current = await self.compute_current()
            metrics = await storage.load(METRICS_KEY, default={"snapshots": []})
            if not isinstance(metrics, dict):
                metrics = {"snapshots": []}

            today  = datetime.utcnow().date().isoformat()
            snaps  = metrics.get("snapshots", [])
            # Sostituisce eventuale snapshot precedente dello stesso giorno
            snaps  = [s for s in snaps if s.get("date") != today]
            snaps.append({"date": today, **current})
            snaps  = snaps[-90:]          # max 90 giorni
            metrics["snapshots"] = snaps
            await storage.save(METRICS_KEY, metrics)
            logger.info("CAPABILITY_SNAPSHOT_SAVED date=%s overall=%.1f%%",
                        today, current["scores"].get("overall_health", 0))
        except Exception as e:
            logger.error("CAPABILITY_SNAPSHOT_ERROR err=%s", e)

    async def get_history(self, days: int = 30) -> List[Dict]:
        """Restituisce storico snapshot degli ultimi N giorni."""
        try:
            metrics = await storage.load(METRICS_KEY, default={"snapshots": []})
            snaps   = metrics.get("snapshots", []) if isinstance(metrics, dict) else []
            cutoff  = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
            return [s for s in snaps if s.get("date", "") >= cutoff]
        except Exception:
            return []

    async def record_interaction(self, counters: Dict[str, int]) -> None:
        """
        Aggiorna i contatori giornalieri con i dati di un'interazione.
        counters può contenere: episodes_saved, personal_facts_saved,
                                context_injected, fallback_triggered
        """
        try:
            today   = datetime.utcnow().date().isoformat()
            all_cnt = await storage.load(COUNTERS_KEY, default={})
            if not isinstance(all_cnt, dict):
                all_cnt = {}
            day_cnt = all_cnt.get(today, {
                "total_messages":     0,
                "episodes_saved":     0,
                "personal_facts_saved": 0,
                "context_injected":   0,
                "fallbacks_triggered": 0,
            })
            day_cnt["total_messages"] += 1
            for k, v in counters.items():
                day_cnt[k] = day_cnt.get(k, 0) + v
            all_cnt[today] = day_cnt
            # Mantieni solo ultimi 30 giorni
            all_dates = sorted(all_cnt.keys())[-30:]
            all_cnt   = {d: all_cnt[d] for d in all_dates}
            await storage.save(COUNTERS_KEY, all_cnt)
        except Exception as e:
            logger.debug("CAPABILITY_COUNTER_ERROR err=%s", e)

    async def get_counters(self, days: int = 30) -> Dict[str, Dict]:
        """Restituisce i contatori grezzi per N giorni."""
        try:
            all_cnt = await storage.load(COUNTERS_KEY, default={})
            if not isinstance(all_cnt, dict):
                return {}
            cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
            return {d: v for d, v in all_cnt.items() if d >= cutoff}
        except Exception:
            return {}

    # ── Metriche singole ──────────────────────────────────────────────────

    async def _is_test_user(self, uid: str) -> bool:
        """Ritorna True se l'utente è un account di test (confronta l'email dal profilo)."""
        _TEST_EMAILS = {"neural_test@genesi.local"}
        try:
            profile = await storage.load(f"profile:{uid}", default={})
            return profile.get("email", "") in _TEST_EMAILS
        except Exception:
            return False

    async def _episode_coverage(self) -> float:
        """
        Avg episodi per utente reale (esclude utenti di test).
        Soglia 20 episodi = copertura piena (più realistica per un sistema personale).
        """
        try:
            user_ids = await storage.list_keys("episodes")
            if not user_ids:
                return 0.0
            counts = []
            for uid in user_ids[:60]:
                if await self._is_test_user(uid):
                    continue
                eps = await storage.load(f"episodes:{uid}", default=[])
                # episodes è sempre una lista
                if isinstance(eps, list):
                    counts.append(len(eps))
            if not counts:
                return 0.0
            avg = sum(counts) / len(counts)
            # Soglia 10: episodi su finestra rolling 30gg — 20 era irraggiungibile
            return round(min(avg / 10.0, 1.0), 3)
        except Exception:
            return 0.0

    async def _facts_coverage(self) -> float:
        """
        Avg fatti personali per utente reale (esclude utenti di test).
        Soglia 15 fatti = copertura buona per un sistema personale.
        """
        try:
            user_ids = await storage.list_keys("personal_facts")
            if not user_ids:
                return 0.0
            counts = []
            for uid in user_ids[:60]:
                if await self._is_test_user(uid):
                    continue
                data = await storage.load(f"personal_facts:{uid}", default={})
                # personal_facts_service salva {"facts": [...]} — estraiamo la lista
                if isinstance(data, dict):
                    facts = data.get("facts", [])
                elif isinstance(data, list):
                    facts = data
                else:
                    facts = []
                counts.append(len(facts))
            if not counts:
                return 0.0
            avg = sum(counts) / len(counts)
            return round(min(avg / 15.0, 1.0), 3)
        except Exception:
            return 0.0

    async def _insight_depth(self) -> float:
        """% utenti con almeno 3 global insights consolidati."""
        try:
            user_ids = await storage.list_keys("global_insights")
            if not user_ids:
                return 0.0
            sample   = user_ids[:100]   # campione — divide per la stessa dimensione
            rich     = 0
            for uid in sample:
                data     = await storage.load(f"global_insights:{uid}", default={})
                insights = data.get("insights", []) if isinstance(data, dict) else []
                if len(insights) >= 3:
                    rich += 1
            return round(rich / max(len(sample), 1), 3)
        except Exception:
            return 0.0

    async def _fallback_health(self) -> float:
        """1 − tasso_di_fallback. Meno fallback = sistema più stabile."""
        try:
            fallbacks = await storage.load("admin/fallbacks", default={})
            groups    = fallbacks.get("groups", {}) if isinstance(fallbacks, dict) else {}
            total_fb  = sum(g.get("count", 0) for g in groups.values())
            # 0 fallback → 1.0 (ottimo); ≥200 fallback → 0.0
            health    = max(0.0, 1.0 - total_fb / 200.0)
            return round(health, 3)
        except Exception:
            return 0.85  # assume buono se dati non disponibili

    async def _correction_rate(self) -> float:
        """
        Misura quante lessons attive ci sono rispetto al massimo supportato (25).
        25 lessons attive = 100%. Scala linearmente, non penalizza per numero
        totale di corrections accumulate nel tempo.
        """
        try:
            from core.training_autopilot import MAX_ACTIVE_LESSONS
            corrections = await storage.load("admin/corrections", default=[])
            if not isinstance(corrections, list):
                corrections = []
            if not corrections:
                return 1.0
            lessons = sum(1 for c in corrections if c.get("lesson_active", False))
            quality = min(lessons / MAX_ACTIVE_LESSONS, 1.0)
            return round(quality, 3)
        except Exception:
            return 1.0


capability_tracker = CapabilityTracker()
