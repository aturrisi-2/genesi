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
MAX_ACTIVE_LESSONS  = 8     # max lessons attive nel prompt contemporaneamente
TRAIN_LESSON_RATIO  = 0.45  # se lessons/total < 45% → valuta training automatico
MIN_UNRESOLVED      = 8     # min corrections irrisolte per avviare il training auto
TRAINING_COOLDOWN_H = 22    # ore minime tra due training automatici consecutivi
CHECK_INTERVAL_S    = 3600  # controlla ogni ora
STARTUP_DELAY_S     = 180   # attesa post-avvio (lascia stabilizzare il server)

AUTOPILOT_KEY       = "admin/autopilot_state"
ADAPTIVE_STATUS_KEY = "admin/adaptive_training_status"

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

        # 2. Rotazione lessons ottimale
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

        sorted_corr = sorted(corrections, key=priority)
        top_ids     = {c["id"] for c in sorted_corr[:MAX_ACTIVE_LESSONS]}

        activated   = 0
        deactivated = 0

        for c in corrections:
            cid        = c["id"]
            is_active  = c.get("lesson_active", False)
            should_be  = cid in top_ids

            if should_be and not is_active:
                ok = await training_engine.toggle_lesson(cid, True)
                if ok:
                    activated += 1
            elif not should_be and is_active:
                ok = await training_engine.toggle_lesson(cid, False)
                if ok:
                    deactivated += 1

        return activated, deactivated

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

            # Dopo il training, ribilancia subito le lessons
            await self._auto_manage_lessons()

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
            "ticks_total":          state.get("ticks_total", 0),
            "next_check_min":       next_check_min,
            "config": {
                "max_lessons":     MAX_ACTIVE_LESSONS,
                "train_threshold": f"{int(TRAIN_LESSON_RATIO*100)}%",
                "cooldown_h":      TRAINING_COOLDOWN_H,
            },
        }


autopilot = TrainingAutopilot()
