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
_DEEP_CONVO_SCRIPT   = Path(__file__).parent.parent / "scripts" / "deep_conversation.py"
TRAINING_USER_EMAIL  = os.getenv("TRAINING_USER_EMAIL",    "alfio.turrisi@gmail.com")
TRAINING_USER_PWD    = os.getenv("TRAINING_USER_PASSWORD", "ZOEennio0810")
TRAINING_ADMIN_EMAIL = os.getenv("TRAINING_ADMIN_EMAIL",   "idappleturrisi@gmail.com")
TRAINING_ADMIN_PWD   = os.getenv("TRAINING_ADMIN_PASSWORD","ZOEennio0810")

DEEP_CONVO_STATUS_KEY   = "admin/deep_convo_training_status"
DEEP_CONVO_MIN_PATTERNS = 4    # soglia: se patterns distillati < 4 → notifica email (non auto-run)
DEEP_CONVO_COOLDOWN_H   = 8    # cooldown tra notifiche consecutive

ENRICH_INTERVAL_H    = 6    # ogni 6h arricchisce il serbatoio da tutte le sorgenti
NOTIFY_COOLDOWN_H    = 24   # max 1 email di notifica al giorno
NOTIFY_OWNER_EMAIL   = os.getenv("NOTIFY_OWNER_EMAIL", "alfio.turrisi@gmail.com")
ADMIN_PANEL_URL      = os.getenv("ADMIN_PANEL_URL", "https://genesi.lucadigitale.eu/admin")

_ENRICH_PROMPT = """\
Analizza questi estratti da conversazioni, episodi, fatti personali e interazioni di gruppo di un utente.
Estrai 3-5 nuovi insight distinti sul suo carattere, abitudini, valori o comportamento.
NON ripetere insight già presenti in questa lista: {existing}

Sorgenti:
{sources}

Rispondi SOLO con JSON valido: {{"insights": ["insight 1", "insight 2", ...]}}
Ogni insight: 1 frase in italiano, personale e specifico. Max 5. Se non c'è nulla di nuovo: {{"insights": []}}
"""


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

        # 4. Arricchimento serbatoio pattern da tutte le sorgenti (ogni ENRICH_INTERVAL_H)
        last_enrich = state.get("last_enrichment")
        run_enrich = True
        if last_enrich:
            try:
                elapsed_h = (datetime.utcnow() - datetime.fromisoformat(last_enrich)).total_seconds() / 3600
                if elapsed_h < ENRICH_INTERVAL_H:
                    run_enrich = False
            except Exception:
                pass
        if run_enrich:
            enriched = await self._enrich_global_insights()
            if enriched > 0:
                actions.append(f"enriched +{enriched} insights")
                logger.info("AUTOPILOT_ENRICH_DONE new_insights=%d", enriched)
            state["last_enrichment"] = now.isoformat()

        # 5. Se serbatoio esaurito → notifica email (NON auto-run)
        dc_should, dc_reason = await self._should_deep_convo(state)
        if dc_should:
            asyncio.create_task(self._notify_tank_empty(state))
            actions.append(f"tank_empty_notified ({dc_reason})")
            logger.info("AUTOPILOT_TANK_EMPTY_NOTIFIED reason=%s", dc_reason)

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

    # ── Deep conversation auto-trigger ────────────────────────────────────────

    async def _should_deep_convo(self, state: dict) -> Tuple[bool, str]:
        """
        Ritorna (True, motivo) se il pool di insights distillati è esaurito.
        Condizioni: patterns < soglia + cooldown passato + nessun deep convo in corso.
        """
        # Nessun lancio se c'è già un deep convo in corso
        dc_status = await storage.load(DEEP_CONVO_STATUS_KEY, default={})
        if isinstance(dc_status, dict) and dc_status.get("status") in ("running", "starting"):
            return False, ""

        # Cooldown tra deep convo automatici
        last_end = state.get("last_deep_convo_end")
        if last_end:
            try:
                elapsed_h = (datetime.utcnow() - datetime.fromisoformat(last_end)).total_seconds() / 3600
                if elapsed_h < DEEP_CONVO_COOLDOWN_H:
                    return False, ""
            except Exception:
                pass

        # Conta i pattern distillati disponibili
        distilled = await storage.load("moltbook:distilled_insights", default={})
        patterns = distilled.get("patterns", []) if isinstance(distilled, dict) else []
        if len(patterns) < DEEP_CONVO_MIN_PATTERNS:
            return True, f"patterns={len(patterns)}<{DEEP_CONVO_MIN_PATTERNS}"

        return False, ""

    async def _run_deep_convo_auto(self, state: dict):
        """Lancia deep_conversation.py in background e aggiorna contatore."""
        try:
            cmd = [
                sys.executable, str(_DEEP_CONVO_SCRIPT),
                "--email",    TRAINING_ADMIN_EMAIL,
                "--password", TRAINING_ADMIN_PWD,
                "--themes",   "12",
                "--pause",    "30",
            ]

            # Aggiorna status per il pannello admin
            dc_status = {
                "status":     "running",
                "started_at": datetime.utcnow().isoformat(),
                "triggered_by": "autopilot",
                "themes": 12,
                "pause": 30.0,
                "output_lines": [],
                "pid": None,
            }
            await storage.save(DEEP_CONVO_STATUS_KEY, dc_status)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            dc_status["pid"] = proc.pid
            await storage.save(DEEP_CONVO_STATUS_KEY, dc_status)

            state["last_deep_convo_start"] = datetime.utcnow().isoformat()
            state["deep_convo_auto_count"] = state.get("deep_convo_auto_count", 0) + 1
            await storage.save(AUTOPILOT_KEY, state)

            logger.info("AUTOPILOT_DEEP_CONVO_STARTED pid=%d count=%d",
                        proc.pid, state["deep_convo_auto_count"])

            await proc.wait()

            state["last_deep_convo_end"]  = datetime.utcnow().isoformat()
            state["last_deep_convo_code"] = proc.returncode
            await storage.save(AUTOPILOT_KEY, state)

            dc_status["status"]       = "completed" if proc.returncode == 0 else "failed"
            dc_status["returncode"]   = proc.returncode
            dc_status["completed_at"] = datetime.utcnow().isoformat()
            await storage.save(DEEP_CONVO_STATUS_KEY, dc_status)

            logger.info("AUTOPILOT_DEEP_CONVO_DONE returncode=%d", proc.returncode)

        except Exception as e:
            logger.error("AUTOPILOT_DEEP_CONVO_ERROR err=%s", e)
            state["last_deep_convo_end"]   = datetime.utcnow().isoformat()
            state["last_deep_convo_error"] = str(e)
            await storage.save(AUTOPILOT_KEY, state)

    # ── Enrichment serbatoio da tutte le sorgenti ─────────────────────────────

    async def _enrich_global_insights(self) -> int:
        """
        Succhia fatti da chat_memory, episodi, personal_facts e storia gruppo Telegram
        → estrae nuovi insights via LLM → li inietta in global_insights dell'utente
        → _distill_user_insights li raccoglie automaticamente al prossimo ciclo.
        Ritorna il numero di nuovi insights aggiunti.
        """
        try:
            from core.llm_service import llm_service
            import json

            user_id = "6028d92a-94f2-4e2f-bcb7-012c861e3ab2"  # Alfio

            # Carica insights esistenti per non duplicare
            gi = await storage.load(f"global_insights:{user_id}", default={})
            existing = gi.get("insights", []) if isinstance(gi, dict) else []

            sources_parts = []

            # 1. Chat memory — ultimi 20 turni
            chat_mem = await storage.load(f"chat_memory:{user_id}", default=[]) or []
            if chat_mem:
                turns = chat_mem[-20:]
                snippets = []
                for m in turns:
                    u = m.get("user_message", "")[:120]
                    if u:
                        snippets.append(f"U: {u}")
                if snippets:
                    sources_parts.append("=== Chat recenti ===\n" + "\n".join(snippets))

            # 2. Episodi
            episodes = await storage.load(f"episodes:{user_id}", default=[]) or []
            if episodes:
                ep_lines = [f"- {e.get('title','')}: {e.get('summary','')[:100]}"
                            for e in episodes[-15:] if e.get("title")]
                if ep_lines:
                    sources_parts.append("=== Episodi ===\n" + "\n".join(ep_lines))

            # 3. Personal facts
            pf = await storage.load(f"personal_facts:{user_id}", default=[]) or []
            if pf:
                pf_lines = [f"- {f.get('key','').replace('_',' ')}: {f.get('value','')}"
                            for f in pf[-20:] if f.get("value")]
                if pf_lines:
                    sources_parts.append("=== Fatti personali ===\n" + "\n".join(pf_lines))

            # 4. Storia gruppo Telegram
            try:
                from core.telegram_group_memory import get_group_history
                GROUP_CHAT_ID = int(os.getenv("TELEGRAM_GROUP_CHAT_ID", "-318483633"))
                if GROUP_CHAT_ID:
                    group_hist = await get_group_history(GROUP_CHAT_ID, limit=15)
                    if group_hist:
                        gh_lines = [f"- {h.get('first_name','?')}: {h.get('text','')[:100]}"
                                    for h in group_hist]
                        sources_parts.append("=== Gruppo Telegram ===\n" + "\n".join(gh_lines))
            except Exception:
                pass

            # 5. Risposte agenti Moltbook (già consolidate)
            mb_insights = await storage.load("moltbook:interaction_insights", default={})
            mb_list = mb_insights.get("insights", []) if isinstance(mb_insights, dict) else []
            if mb_list:
                sources_parts.append("=== Feedback agenti Moltbook ===\n" +
                                     "\n".join(f"- {i}" for i in mb_list[:6]))

            if not sources_parts:
                return 0

            sources_text = "\n\n".join(sources_parts)
            existing_str = "; ".join(existing[:10]) if existing else "nessuno"
            prompt = _ENRICH_PROMPT.format(existing=existing_str, sources=sources_text)

            raw = await llm_service._call_model(
                "openai/gpt-4o-mini", prompt, "", user_id="autopilot-enrich", route="memory"
            )
            if not raw:
                return 0

            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            parsed = json.loads(clean.strip())
            new_insights = [i for i in parsed.get("insights", [])
                            if isinstance(i, str) and len(i) > 15 and i not in existing]

            if not new_insights:
                return 0

            # Merge: aggiungi in coda, mantieni max 30 insights totali
            merged = (existing + new_insights)[-30:]
            gi["insights"] = merged
            gi["last_consolidated_at"] = datetime.utcnow().isoformat()
            gi["message_count"] = gi.get("message_count", 0) + len(new_insights)
            await storage.save(f"global_insights:{user_id}", gi)

            # Invalida cache distilled_insights per forzare ricalcolo al prossimo ciclo
            cache = await storage.load("moltbook:distilled_insights", default={})
            if isinstance(cache, dict):
                cache["distilled_at"] = "2000-01-01T00:00:00"  # forza scadenza
                await storage.save("moltbook:distilled_insights", cache)

            return len(new_insights)

        except Exception as e:
            logger.debug("AUTOPILOT_ENRICH_ERROR err=%s", e)
            return 0

    # ── Notifica email quando serbatoio è vuoto ────────────────────────────────

    async def _notify_tank_empty(self, state: dict):
        """
        Invia una mail ad Alfio quando i pattern Moltbook sono esauriti.
        Include situazione attuale + link per lanciare manualmente il deep_convo.
        Rispetta un cooldown di NOTIFY_COOLDOWN_H ore per non spammare.
        """
        try:
            # Cooldown notifiche
            last_notify = state.get("last_tank_notify")
            if last_notify:
                elapsed_h = (datetime.utcnow() - datetime.fromisoformat(last_notify)).total_seconds() / 3600
                if elapsed_h < NOTIFY_COOLDOWN_H:
                    return

            from core.notification_email import send_reminder_email
            import json

            # Raccoglie statistiche per la mail
            distilled = await storage.load("moltbook:distilled_insights", default={})
            patterns = distilled.get("patterns", []) if isinstance(distilled, dict) else []
            mb_insights = await storage.load("moltbook:interaction_insights", default={})
            mb_count = len(mb_insights.get("insights", [])) if isinstance(mb_insights, dict) else 0
            ilog = await storage.load("moltbook:interaction_log", default={})
            interactions = len(ilog.get("interactions", [])) if isinstance(ilog, dict) else 0
            gi = await storage.load("global_insights:6028d92a-94f2-4e2f-bcb7-012c861e3ab2", default={})
            gi_count = len(gi.get("insights", [])) if isinstance(gi, dict) else 0

            body = f"""Ciao Alfio,

Il serbatoio di pattern Moltbook di Genesi è esaurito e l'arricchimento automatico non ha trovato abbastanza materiale nuovo.

Situazione attuale:
- Pattern nel serbatoio: {len(patterns)}
- Insights globali: {gi_count}
- Insights da agenti Moltbook: {mb_count}
- Interazioni Moltbook registrate: {interactions}

Per riempire il serbatoio puoi lanciare manualmente la deep conversation dal pannello admin:
{ADMIN_PANEL_URL}

Questa è una notifica automatica di Genesi. Non rispondere a questa email.
"""
            await send_reminder_email(
                NOTIFY_OWNER_EMAIL,
                body,
                user_name="Alfio"
            )
            state["last_tank_notify"] = datetime.utcnow().isoformat()
            await storage.save(AUTOPILOT_KEY, state)
            logger.info("AUTOPILOT_TANK_NOTIFY_SENT to=%s", NOTIFY_OWNER_EMAIL)

        except Exception as e:
            logger.debug("AUTOPILOT_NOTIFY_ERROR err=%s", e)

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
            "deep_convo": {
                "auto_count":  state.get("deep_convo_auto_count", 0),
                "last_start":  state.get("last_deep_convo_start"),
                "last_end":    state.get("last_deep_convo_end"),
                "last_code":   state.get("last_deep_convo_code"),
                "min_patterns_threshold": DEEP_CONVO_MIN_PATTERNS,
                "cooldown_h":            DEEP_CONVO_COOLDOWN_H,
            },
            "config": {
                "max_lessons":        MAX_ACTIVE_LESSONS,
                "train_threshold":    f"{int(TRAIN_LESSON_RATIO*100)}%",
                "cooldown_h":         TRAINING_COOLDOWN_H,
                "llm_curator_every_h": LLM_CURATOR_INTERVAL_H,
            },
        }


autopilot = TrainingAutopilot()
