"""
ADMIN IMPROVEMENT SCORE — Genesi
Calcola il punteggio composito di auto-miglioramento (0–100) aggregando
tutti i processi attivi: lab cycle, global insights, training, moltbook,
memoria episodica, personal facts.
"""

from datetime import datetime
from fastapi import APIRouter, Depends
from auth.router import require_admin
from auth.models import AuthUser
from core.storage import storage

router = APIRouter(prefix="/admin/improvement", tags=["admin-improvement"])

# ── Pesi componenti (sommano a 1.0) ────────────────────────────────────────
_WEIGHTS = {
    "lab_rules":       0.28,   # Regole generate dal lab feedback cycle
    "global_insights": 0.22,   # Insights cross-conversazione consolidati
    "moltbook":        0.18,   # Attività + feedback tecnico da Moltbook
    "training":        0.16,   # Lessons attive dal training engine
    "memory_depth":    0.16,   # Episodi + personal facts accumulati
}

# ── Target per score 100 su ogni componente ────────────────────────────────
_TARGET_LAB_RULES       = 25    # regole attive
_TARGET_INSIGHTS_PER_U  = 6     # insights medi per utente
_TARGET_HB              = 150   # heartbeat totali
_TARGET_TECH_FB         = 12    # feedback tecnici da Moltbook
_TARGET_LESSONS         = 20    # lessons attive training
_TARGET_FACTS_PER_U     = 40    # personal facts medi per utente
_TARGET_EPISODES_PER_U  = 20    # episodi medi per utente


def _pct(value: float, target: float) -> float:
    """Percentuale 0-100, cappata a 100."""
    if target <= 0:
        return 0.0
    return min(value / target * 100, 100.0)


async def _compute_score() -> dict:
    components = {}

    # ── 1. Lab rules ───────────────────────────────────────────────────────
    try:
        import json as _json
        from pathlib import Path as _Path
        # Le regole sono in lab/global_prompt.json (feedback_rules) + stato ciclo
        gp_path = _Path("lab/global_prompt.json")
        gp_data = _json.loads(gp_path.read_text(encoding="utf-8")) if gp_path.exists() else {}
        active_rules = len(gp_data.get("feedback_rules", []))
        # Conteggio osservazioni da fallbacks
        fb_path = _Path("memory/admin/fallbacks.json")
        fb_data = _json.loads(fb_path.read_text(encoding="utf-8")) if fb_path.exists() else []
        total_obs = len(fb_data) if isinstance(fb_data, list) else 0
        rule_score = _pct(active_rules, _TARGET_LAB_RULES)
        components["lab_rules"] = {
            "score": rule_score,
            "label": "Regole Lab",
            "detail": f"{active_rules} regole attive, {total_obs} osservazioni",
            "value": active_rules,
        }
    except Exception:
        components["lab_rules"] = {"score": 0, "label": "Regole Lab", "detail": "N/D", "value": 0}

    # ── 2. Global insights ─────────────────────────────────────────────────
    try:
        user_ids = await storage.list_keys("global_insights")
        insight_counts = []
        for uid in user_ids:
            d = await storage.load(f"global_insights:{uid}", default={})
            insight_counts.append(len(d.get("insights", [])))
        avg_insights = sum(insight_counts) / max(len(insight_counts), 1)
        gi_score = _pct(avg_insights, _TARGET_INSIGHTS_PER_U)
        components["global_insights"] = {
            "score": gi_score,
            "label": "Global Insights",
            "detail": f"{len(user_ids)} utenti · media {avg_insights:.1f} insights",
            "value": avg_insights,
        }
    except Exception:
        components["global_insights"] = {"score": 0, "label": "Global Insights", "detail": "N/D", "value": 0}

    # ── 3. Moltbook ────────────────────────────────────────────────────────
    try:
        mb_state = await storage.load("moltbook:state", default={"heartbeat_count": 0})
        hb = mb_state.get("heartbeat_count", 0)
        mb_insights = await storage.load("moltbook:interaction_insights", default={})
        tech_fb = len(mb_insights.get("technical_feedback", []))
        hb_score  = _pct(hb, _TARGET_HB)
        tech_score = _pct(tech_fb, _TARGET_TECH_FB)
        mb_score = (hb_score + tech_score) / 2
        components["moltbook"] = {
            "score": mb_score,
            "label": "Moltbook",
            "detail": f"{hb} heartbeat · {tech_fb} feedback tecnici",
            "value": hb,
        }
    except Exception:
        components["moltbook"] = {"score": 0, "label": "Moltbook", "detail": "N/D", "value": 0}

    # ── 4. Training lessons ────────────────────────────────────────────────
    try:
        from core.training_engine import training_engine
        stats = await training_engine.get_stats()
        active_lessons = stats.get("active_lessons", 0)
        tr_score = _pct(active_lessons, _TARGET_LESSONS)
        components["training"] = {
            "score": tr_score,
            "label": "Training Lessons",
            "detail": f"{active_lessons} lessons attive",
            "value": active_lessons,
        }
    except Exception:
        components["training"] = {"score": 0, "label": "Training", "detail": "N/D", "value": 0}

    # ── 5. Memory depth (episodes + personal facts) ────────────────────────
    try:
        ep_ids  = await storage.list_keys("episodes")
        pf_ids  = await storage.list_keys("personal_facts")
        ep_counts, pf_counts = [], []
        for uid in ep_ids:
            d = await storage.load(f"episodes:{uid}", default=[])
            ep_counts.append(len(d) if isinstance(d, list) else 0)
        for uid in pf_ids:
            d = await storage.load(f"personal_facts:{uid}", default={})
            pf_counts.append(len(d.get("facts", [])))
        avg_ep = sum(ep_counts) / max(len(ep_counts), 1)
        avg_pf = sum(pf_counts) / max(len(pf_counts), 1)
        ep_score = _pct(avg_ep, _TARGET_EPISODES_PER_U)
        pf_score = _pct(avg_pf, _TARGET_FACTS_PER_U)
        mem_score = (ep_score + pf_score) / 2
        components["memory_depth"] = {
            "score": mem_score,
            "label": "Memoria",
            "detail": f"media {avg_ep:.0f} episodi · {avg_pf:.0f} fatti/utente",
            "value": (avg_ep + avg_pf) / 2,
        }
    except Exception:
        components["memory_depth"] = {"score": 0, "label": "Memoria", "detail": "N/D", "value": 0}

    # ── Score totale pesato ────────────────────────────────────────────────
    total = sum(components[k]["score"] * _WEIGHTS[k] for k in _WEIGHTS)
    total = round(min(total, 100), 1)

    return {"score": total, "components": components}


@router.get("/score")
async def get_improvement_score(_: AuthUser = Depends(require_admin)):
    """Score composito 0-100 di auto-miglioramento + storico per il hold."""
    now_str = datetime.utcnow().isoformat()

    # Calcola score attuale
    result = await _compute_score()
    current = result["score"]
    components = result["components"]

    # Carica storico — il "previous" è l'ultimo punto salvato
    history = await storage.load("admin:improvement_score_history",
                                 default={"entries": []})
    entries = history.get("entries", [])
    previous = entries[-1]["score"] if entries else None

    # Salva nuovo punto (max 90 entries → ~30gg a 8 misure/die)
    entries.append({"score": current, "ts": now_str})
    history["entries"] = entries[-90:]
    await storage.save("admin:improvement_score_history", history)

    return {
        "score": current,
        "previous": previous,
        "delta": round(current - previous, 1) if previous is not None else None,
        "components": components,
        "weights": _WEIGHTS,
        "computed_at": now_str,
    }
