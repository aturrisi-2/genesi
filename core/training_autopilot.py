"""
TRAINING AUTOPILOT — Genesi
Gestione automatica di lessons, snapshot giornaliero e training adattivo.
Gira in background ogni ora. Zero intervento manuale necessario.

Logica:
  Ogni ora:
    1. Snapshot giornaliero (1x/giorno)
    2. Rotazione lessons: mantieni le MAX_ACTIVE_LESSONS più utili attive
    3. Training automatico se qualità sotto soglia e cooldown passato
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Tuple

from core.storage import storage
from core.capability_tracker import capability_tracker
from core.training_engine import training_engine

logger = logging.getLogger(__name__)

# ── Configurazione ─────────────────────────────────────────────────────────────
MAX_ACTIVE_LESSONS     = 25    # max lessons attive nel prompt contemporaneamente
TRAIN_LESSON_RATIO     = 0.45  # se lessons/total < 45% → valuta training automatico
MIN_UNRESOLVED         = 8     # min corrections irrisolte per avviare il training auto
TRAINING_COOLDOWN_H    = 22    # ore minime tra due training automatici consecutivi
LLM_CURATOR_INTERVAL_H = 6    # ore tra una curazione LLM e l'altra
CHECK_INTERVAL_S       = 3600  # controlla ogni ora
STARTUP_DELAY_S        = 180   # attesa post-avvio (lascia stabilizzare il server)

AUTOPILOT_KEY       = "admin/autopilot_state"
ADAPTIVE_STATUS_KEY = "admin/adaptive_training_status"


def age_lbl(days) -> str:
    """Etichetta leggibile per l'età di una correction."""
    if days == "?":
        return "[età?]"
    if days == 0:
        return "[oggi]"
    if days <= 7:
        return f"[{days}gg]"
    return f"[{days}gg]"

_SCRIPT_PATH         = Path(__file__).parent.parent / "scripts" / "training_marathon.py"
TRAINING_USER_EMAIL  = os.getenv("TRAINING_USER_EMAIL",    "alfio.turrisi@gmail.com")
TRAINING_USER_PWD    = os.getenv("TRAINING_USER_PASSWORD", "ZOEennio0810")
TRAINING_ADMIN_EMAIL = os.getenv("TRAINING_ADMIN_EMAIL",   "idappleturrisi@gmail.com")
TRAINING_ADMIN_PWD   = os.getenv("TRAINING_ADMIN_PASSWORD","ZOEennio0810")


class TrainingAutopilot:

    # ── Loop principale ────────────────────────────────────────────────────────

    async def run_background_loop(self):
        """Avviato al boot del server. Gira per sempre, controlla ogni ora."""
        await asyncio.sleep(STARTUP_DELAY_S)
        logger.info("AUTOPILOT_STARTED interval=%ds max_lessons=%d", CHECK_INTERVAL_S, MAX_ACTIVE_LESSONS)
        while True:
            try:
                await self._tick()
            except Exception as e:
                logger.error("AUTOPILOT_TICK_ERROR err=%s", e)
            await asyncio.sleep(CHECK_INTERVAL_S)

    async def _tick(self):
        now   = datetime.utcnow()
        today = date.today().isoformat()
        state = await storage.load(AUTOPILOT_KEY, default={})
        if not isinstance(state, dict):
            state = {}

        actions = []

        # 1. Snapshot giornaliero
        if state.get("last_snapshot") != today:
            await capability_tracker.save_snapshot()
            state["last_snapshot"] = today
            actions.append("snapshot_saved")
            logger.info("AUTOPILOT_SNAPSHOT date=%s", today)

        # 2. Curazione LLM (ogni LLM_CURATOR_INTERVAL_H) + fallback euristica
        last_curated = state.get("last_llm_curation")
        run_llm_curation = True
        if last_curated:
            try:
                elapsed_h = (datetime.utcnow() - datetime.fromisoformat(last_curated)).total_seconds() / 3600
                if elapsed_h < LLM_CURATOR_INTERVAL_H:
                    run_llm_curation = False
            except Exception:
                pass

        if run_llm_curation:
            activated, deactivated, curation_reason = await self._llm_curate_lessons()
            if activated or deactivated:
                actions.append(f"llm_curator +{activated} -{deactivated}")
                logger.info("AUTOPILOT_LLM_CURATOR activated=%d deactivated=%d reason=%s",
                            activated, deactivated, curation_reason[:80] if curation_reason else "")
            state["last_llm_curation"] = now.isoformat()
            state["last_curation_reason"] = curation_reason or ""
        else:
            # Fallback euristica ogni ora per riempire slot vuoti
            activated, deactivated = await self._auto_manage_lessons()
            if activated or deactivated:
                actions.append(f"lessons +{activated} -{deactivated}")
                logger.info("AUTOPILOT_LESSONS activated=%d deactivated=%d", activated, deactivated)

        # 3. Training automatico se necessario
        should, reason = await self._should_train(state)
        if should:
            asyncio.create_task(self._run_auto_training(state))
            actions.append(f"training_triggered ({reason})")
            logger.info("AUTOPILOT_TRAINING_TRIGGERED reason=%s", reason)

        # Persiste stato
        state["last_tick"]    = now.isoformat()
        state["last_actions"] = actions if actions else ["checked_ok"]
        state["ticks_total"]  = state.get("ticks_total", 0) + 1
        await storage.save(AUTOPILOT_KEY, state)

    # ── Gestione automatica lessons ────────────────────────────────────────────

    async def _auto_manage_lessons(self) -> Tuple[int, int]:
        """
        Mantiene attive le MAX_ACTIVE_LESSONS corrections più utili.
        Priorità: categoria più debole (rank basso) + correction più recente.
        Attiva quelle mancanti, disattiva quelle in eccesso o a bassa priorità.
        """
        corrections = await storage.load("admin/corrections", default=[])
        if not isinstance(corrections, list) or not corrections:
            return 0, 0

        # Rank di debolezza per categoria (indice 0 = più debole)
        try:
            weak = await training_engine.get_weak_categories(top_n=30)
            weak_rank = {w["category"]: i for i, w in enumerate(weak)}
        except Exception:
            weak_rank = {}

        def priority(c: dict) -> float:
            """Score basso = alta priorità = deve essere attiva."""
            cat  = c.get("category", "altro")
            rank = weak_rank.get(cat, 99)
            try:
                age = (datetime.utcnow() - datetime.fromisoformat(c["timestamp"])).days
            except Exception:
                age = 30
            return rank * 10 + min(age, 30)

        # Lessons pinnate manualmente dall'admin: non vengono mai toccate dall'autopilot
        pinned_ids  = {c["id"] for c in corrections if c.get("lesson_pinned")}
        # Slot liberi per la rotazione automatica
        free_slots  = max(0, MAX_ACTIVE_LESSONS - len(pinned_ids))
        # Considera solo le non-pinnate per la selezione automatica
        unpinned    = [c for c in corrections if c["id"] not in pinned_ids]
        sorted_corr = sorted(unpinned, key=priority)
        top_ids     = pinned_ids | {c["id"] for c in sorted_corr[:free_slots]}

        # Calcola i cambiamenti necessari senza toccare il disco
        changes = {}
        for c in corrections:
            cid       = c["id"]
            if cid in pinned_ids:
                continue  # mai toccare le lessons pinnate
            is_active = c.get("lesson_active", False)
            should_be = cid in top_ids
            if should_be and not is_active:
                changes[cid] = True
            elif not should_be and is_active:
                changes[cid] = False

        # Un solo load+save per tutti i cambiamenti
        activated, deactivated = await training_engine.batch_toggle_lessons(changes)
        return activated, deactivated

    # ── Curazione LLM autonoma delle lessons ──────────────────────────────────

    async def _llm_curate_lessons(self) -> Tuple[int, int, str]:
        """
        Usa il LLM per scegliere autonomamente quali lessons attivare/disattivare.
        Analizza l'intero pool di corrections e decide quali patterns sistemici
        richiedono rinforzo attivo nel prompt.
        Ritorna (activated, deactivated, reason_text).
        """
        try:
            corrections = await storage.load("admin/corrections", default=[])
            if not isinstance(corrections, list) or not corrections:
                return 0, 0, ""

            # Prepara riassunto compatto per il LLM (evita prompt troppo lunghi)
            pinned_ids = {c["id"] for c in corrections if c.get("lesson_pinned")}
            active_ids = {c["id"] for c in corrections if c.get("lesson_active")}

            # Raggruppa per categoria con statistiche
            from collections import defaultdict
            cat_stats: dict = defaultdict(lambda: {"total": 0, "active": 0, "ids": [], "samples": []})
            for c in corrections:
                cat = c.get("category", "altro")
                cat_stats[cat]["total"] += 1
                if c.get("lesson_active"):
                    cat_stats[cat]["active"] += 1
                # Aggiungi sample (max 3 per categoria) con ID
                if len(cat_stats[cat]["samples"]) < 3:
                    try:
                        age_d = (datetime.utcnow() - datetime.fromisoformat(c["timestamp"])).days
                    except Exception:
                        age_d = "?"
                    cat_stats[cat]["samples"].append({
                        "id": c["id"],
                        "age_days": age_d,
                        "msg": c.get("input_message", "")[:80],
                        "fix": c.get("correct_response", "")[:60],
                        "active": c.get("lesson_active", False),
                        "pinned": c.get("lesson_pinned", False),
                    })
                cat_stats[cat]["ids"].append(c["id"])

            # Formatta il contesto per il LLM
            ctx_lines = []
            for cat, stats in sorted(cat_stats.items(), key=lambda x: -x[1]["total"]):
                ctx_lines.append(
                    f"\nCategoria: {cat} | Totale: {stats['total']} | Attive: {stats['active']}"
                )
                for s in stats["samples"]:
                    pin_flag = " [PINNATA]" if s["pinned"] else ""
                    act_flag = " ✓" if s["active"] else ""
                    ctx_lines.append(
                        f"  id={s['id'][:8]}  {age_lbl(s['age_days'])} msg='{s['msg']}' fix='{s['fix']}'{act_flag}{pin_flag}"
                    )

            corrections_ctx = "\n".join(ctx_lines)

            system_prompt = f"""\
Sei il sistema di auto-miglioramento di Genesi, un assistente AI personale italiano.
Il tuo compito: analizzare le corrections (errori identificati + fix) e decidere quali attivare come lessons attive nel prompt LLM per massimizzare il miglioramento.

REGOLE:
- Puoi attivare fino a {MAX_ACTIVE_LESSONS} lessons in totale (attualmente attive: {len(active_ids)})
- Le lessons [PINNATE] sono protette: NON includerle in "deactivate"
- Attiva corrections che rappresentano PATTERN RICORRENTI (categoria con molte corrections irrisolte)
- Attiva corrections RECENTI (< 7 giorni) che correggono errori attivi
- Disattiva lessons di categorie già risolte (pochi errori nuovi) per fare spazio
- Massimizza la copertura su categorie deboli

CORRECTIONS DISPONIBILI (raggruppate per categoria):
{corrections_ctx}

Rispondi SOLO con JSON valido (niente altro testo):
{{
  "activate": ["full_id_1", "full_id_2", ...],
  "deactivate": ["full_id_3", ...],
  "reason": "breve spiegazione (max 2 righe) della logica di selezione"
}}"""

            # Ricostruisci mappa id → correction per recuperare gli ID completi
            id_map = {c["id"]: c for c in corrections}

            from core.llm_service import llm_service
            import json as _json
            raw = await llm_service._call_model(
                "openai/gpt-4o-mini",
                system_prompt,
                "Analizza le corrections e scegli le lessons ottimali.",
                user_id="system",
                route="memory",
            )
            if not raw:
                raise ValueError("LLM no response")

            # Estrai JSON dalla risposta
            raw_strip = raw.strip()
            if "```" in raw_strip:
                raw_strip = raw_strip.split("```")[1]
                if raw_strip.startswith("json"):
                    raw_strip = raw_strip[4:]
            data = _json.loads(raw_strip)

            to_activate   = [i for i in data.get("activate", [])   if i in id_map and i not in pinned_ids]
            to_deactivate = [i for i in data.get("deactivate", []) if i in id_map and i not in pinned_ids]
            reason        = data.get("reason", "")

            # Applica i cambiamenti rispettando il cap
            current_active_non_pinned = [i for i in active_ids if i not in pinned_ids]
            # Considera attivazioni entro il cap
            free = MAX_ACTIVE_LESSONS - len(pinned_ids)
            # Rimuovi prima quelli da disattivare, poi aggiungi quelli da attivare
            will_active = set(current_active_non_pinned) - set(to_deactivate)
            for aid in to_activate:
                if len(will_active) < free:
                    will_active.add(aid)

            changes = {}
            for cid, c in id_map.items():
                if cid in pinned_ids:
                    continue
                is_active  = c.get("lesson_active", False)
                should_be  = cid in will_active
                if should_be and not is_active:
                    changes[cid] = True
                elif not should_be and is_active:
                    changes[cid] = False

            activated, deactivated = await training_engine.batch_toggle_lessons(changes)
            logger.info("LLM_LESSON_CURATOR_OK activated=%d deactivated=%d reason=%s",
                        activated, deactivated, reason[:100])
            return activated, deactivated, reason

        except Exception as e:
            logger.warning("LLM_LESSON_CURATOR_FAIL err=%s — fallback to heuristic", str(e)[:80])
            # Fallback all'euristica
            act, deact = await self._auto_manage_lessons()
            return act, deact, f"[fallback euristico: {str(e)[:60]}]"

    # ── Trigger automatico training ────────────────────────────────────────────

    async def _should_train(self, state: dict) -> Tuple[bool, str]:
        """
        Ritorna (True, motivo) se è il momento di lanciare un training automatico.
        Condizioni: qualità bassa + cooldown passato + nessun training in corso.
        """
        # Nessun training se c'è già uno in corso (manuale o automatico)
        adaptive = await storage.load(ADAPTIVE_STATUS_KEY, default={})
        if isinstance(adaptive, dict) and adaptive.get("status") in ("running", "starting"):
            return False, ""

        # Cooldown tra training automatici
        last_end = state.get("last_auto_training_end")
        if last_end:
            try:
                elapsed_h = (datetime.utcnow() - datetime.fromisoformat(last_end)).total_seconds() / 3600
                if elapsed_h < TRAINING_COOLDOWN_H:
                    return False, ""
            except Exception:
                pass

        # Analisi qualità corrections
        corrections = await storage.load("admin/corrections", default=[])
        if not isinstance(corrections, list):
            return False, ""

        total      = len(corrections)
        if total == 0:
            return False, ""

        lessons    = sum(1 for c in corrections if c.get("lesson_active", False))
        unresolved = total - lessons
        ratio      = lessons / total

        if unresolved >= MIN_UNRESOLVED and ratio < TRAIN_LESSON_RATIO:
            return True, f"ratio={ratio:.0%} unresolved={unresolved}"

        return False, ""

    async def _run_auto_training(self, state: dict):
        """Lancia il marathon adattivo in background e aggiorna lo stato autopilot."""
        try:
            weak      = await training_engine.get_weak_categories(top_n=3)
            cat_names = [w["category"] for w in weak]
            cats_str  = ",".join(cat_names)

            cmd = [
                sys.executable, str(_SCRIPT_PATH),
                "--email",          TRAINING_USER_EMAIL,
                "--password",       TRAINING_USER_PWD,
                "--admin-email",    TRAINING_ADMIN_EMAIL,
                "--admin-password", TRAINING_ADMIN_PWD,
                "--categories",     cats_str,
                "--pause",          "4",
                "--auto-lesson",
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            state["last_auto_training_start"] = datetime.utcnow().isoformat()
            state["last_auto_training_cats"]  = cat_names
            await storage.save(AUTOPILOT_KEY, state)

            await proc.wait()

            state["last_auto_training_end"]  = datetime.utcnow().isoformat()
            state["last_auto_training_code"] = proc.returncode
            await storage.save(AUTOPILOT_KEY, state)

            logger.info("AUTOPILOT_TRAINING_DONE returncode=%d cats=%s", proc.returncode, cat_names)

            # Dopo il training, il curatore LLM rivaluta subito le lessons
            await self._llm_curate_lessons()

        except Exception as e:
            logger.error("AUTOPILOT_TRAINING_ERROR err=%s", e)
            state["last_auto_training_end"]   = datetime.utcnow().isoformat()
            state["last_auto_training_error"] = str(e)
            await storage.save(AUTOPILOT_KEY, state)

    # ── Status per la dashboard ────────────────────────────────────────────────

    async def get_status(self) -> dict:
        state = await storage.load(AUTOPILOT_KEY, default={})
        if not isinstance(state, dict):
            state = {}

        # Calcola "prossimo check tra X minuti"
        last_tick = state.get("last_tick")
        next_check_min = None
        if last_tick:
            try:
                elapsed_s = (datetime.utcnow() - datetime.fromisoformat(last_tick)).total_seconds()
                remaining_s = max(0, CHECK_INTERVAL_S - elapsed_s)
                next_check_min = int(remaining_s / 60)
            except Exception:
                pass

        return {
            "enabled":              True,
            "last_tick":            state.get("last_tick"),
            "last_actions":         state.get("last_actions", []),
            "last_snapshot":        state.get("last_snapshot"),
            "last_training_start":  state.get("last_auto_training_start"),
            "last_training_end":    state.get("last_auto_training_end"),
            "last_training_cats":   state.get("last_auto_training_cats", []),
            "last_training_code":   state.get("last_auto_training_code"),
            "last_llm_curation":    state.get("last_llm_curation"),
            "last_curation_reason": state.get("last_curation_reason", ""),
            "ticks_total":          state.get("ticks_total", 0),
            "next_check_min":       next_check_min,
            "config": {
                "max_lessons":        MAX_ACTIVE_LESSONS,
                "train_threshold":    f"{int(TRAIN_LESSON_RATIO*100)}%",
                "cooldown_h":         TRAINING_COOLDOWN_H,
                "llm_curator_every_h": LLM_CURATOR_INTERVAL_H,
            },
        }


autopilot = TrainingAutopilot()
