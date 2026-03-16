"""
PREDICTIVE ENGINE — Genesi
Implementa il Processing Predittivo (PP) ispirato alla cognizione naturale.

Principio: dopo ogni turno Genesi genera un'ipotesi su cosa dirà l'utente
nel turno successivo (world model). Quando arriva il messaggio reale, misura
la "sorpresa" (errore di predizione):
  - Alta sorpresa → input inatteso → più peso nell'aggiornamento del contesto
  - Bassa sorpresa → pattern confermato → alta confidenza, flusso normale

Shadow phase (primi SHADOW_TURNS turni per utente):
  Genera predizioni ma non le inietta nel prompt. Serve per calibrare il modello
  prima di influenzare il comportamento.

Dopo la shadow phase: se accuracy >= MIN_ACCURACY, inietta un hint soft nel
contesto ("l'utente potrebbe voler approfondire X") — Genesi può ignorarlo
se il messaggio reale va in un'altra direzione.

Fail-silent: qualsiasi errore non interrompe il flusso chat.
"""

import logging
from datetime import datetime
from typing import Optional

from core.storage import storage
from core.log import log as _slog

logger = logging.getLogger("genesi")

# ── Configurazione ─────────────────────────────────────────────────────────────
STORAGE_KEY      = "predictions:{user_id}"
MAX_HISTORY      = 30    # valutazioni di accuratezza da conservare
SHADOW_TURNS     = 12    # turni in shadow mode (nessuna iniezione nel prompt)
MIN_ACCURACY     = 0.08  # soglia minima di accuratezza per iniettare l'hint
MAX_RECENT_TURNS = 5     # turni recenti usati per generare la predizione

# Stop words italiane (ignorate nel calcolo di sorpresa)
_STOP_IT = {
    "il","la","lo","i","gli","le","un","una","uno","di","da","a","in","e",
    "che","non","mi","ti","si","ci","vi","è","ho","ha","sono","stai","ma",
    "per","con","su","tra","fra","al","del","dei","degli","della","delle",
    "questo","questa","questi","queste","quello","quella","come","quando",
    "dove","perché","perche","cosa","chi","qual","quale","quali","poi",
    "anche","però","se","no","sì","ok","va","già","mio","mia","tuo","tua",
}


class PredictiveEngine:
    """
    Motore di Processing Predittivo.
    Tutti i metodi sono fail-silent: non alzano mai eccezioni verso il caller.
    """

    # ── Assessment dell'input in arrivo ────────────────────────────────────────

    async def assess(self, user_id: str, user_message: str) -> dict:
        """
        Valuta quanto il messaggio è sorprendente rispetto alla predizione attesa.
        Ritorna: surprise_score (0=atteso, 1=sorprendente), prediction, shadow.
        Chiamato all'arrivo di ogni messaggio, prima dell'elaborazione.
        """
        try:
            data = await self._load(user_id)
            prediction = data.get("next_turn_prediction", "")

            if not prediction:
                return {"surprise_score": 0.5, "prediction": "", "shadow": True}

            surprise = self._compute_surprise(user_message, prediction)

            # Aggiorna history accuratezza (accuracy = 1 - surprise)
            history = data.get("accuracy_history", [])
            history.append(round(1.0 - surprise, 3))
            data["accuracy_history"] = history[-MAX_HISTORY:]
            data["last_surprise_score"] = round(surprise, 3)
            data["total_assessments"]   = data.get("total_assessments", 0) + 1

            shadow = data["total_assessments"] <= SHADOW_TURNS
            await storage.save(STORAGE_KEY.format(user_id=user_id), data)

            _slog("PREDICTIVE_ASSESS",
                  user=user_id,
                  surprise=round(surprise, 3),
                  shadow=shadow,
                  total=data["total_assessments"])
            return {
                "surprise_score": surprise,
                "prediction":     prediction,
                "shadow":         shadow,
                "total":          data["total_assessments"],
            }
        except Exception as e:
            logger.debug("PREDICTIVE_ASSESS_ERROR user=%s err=%s", user_id, e)
            return {"surprise_score": 0.5, "prediction": "", "shadow": True}

    def _compute_surprise(self, actual: str, prediction: str) -> float:
        """
        Surprise score 0-1.
        Formula soft: anche 1 keyword condivisa = partial match (0.45).
        Il linguaggio naturale ha bassa ripetizione esatta tra predizione e realtà,
        quindi la Jaccard pura darebbe 1.0 quasi sempre — usiamo una scala a step.

        0.0  = predizione centrata (Jaccard ≥ 0.25)
        0.45 = partial match (1-2 keyword in comune)
        0.85 = nessuna parola in comune — alta sorpresa
        """
        def tokens(text: str):
            return {
                w.lower() for w in text.split()
                if len(w) > 2 and w.lower() not in _STOP_IT
            }

        a = tokens(actual)
        p = tokens(prediction)

        if not a or not p:
            return 0.5

        intersection = a & p
        union        = a | p
        jaccard      = len(intersection) / len(union) if union else 0.0

        if jaccard >= 0.25:
            return round(1.0 - jaccard, 3)   # buona previsione
        elif len(intersection) >= 1:
            return 0.45                        # almeno 1 keyword in comune
        else:
            return 0.85                        # nessun overlap

    # ── Generazione predizione (background, dopo ogni turno) ───────────────────

    async def update_prediction(
        self,
        user_id:            str,
        user_message:       str,
        assistant_response: str,
    ) -> None:
        """
        Genera la predizione per il PROSSIMO turno dell'utente.
        Chiamato in background dopo ogni risposta — usa gpt-4o-mini, fail-silent.
        """
        try:
            from core.llm_service import llm_service

            data = await self._load(user_id)

            # Aggiorna buffer turni recenti
            turns = data.get("recent_turns", [])
            turns.append({
                "user":      user_message[:250],
                "assistant": assistant_response[:250],
            })
            data["recent_turns"] = turns[-MAX_RECENT_TURNS:]

            turns_text = "\n".join(
                f"Utente: {t['user']}\nGenesi: {t['assistant']}"
                for t in data["recent_turns"]
            )

            prediction = await llm_service._call_model(
                "openai/gpt-4o-mini",
                (
                    "Sei un sistema predittivo integrato in un assistente personale. "
                    "Analizza la conversazione e prevedi in UNA frase breve e specifica "
                    "cosa dirà o chiederà l'utente nel prossimo messaggio. "
                    "Rispondi SOLO con la previsione, nessuna altra parola."
                ),
                (
                    f"Conversazione recente:\n{turns_text}\n\n"
                    "Cosa dirà probabilmente l'utente nel prossimo messaggio?"
                ),
                user_id=user_id,
                route="memory",
            )

            if prediction:
                data["next_turn_prediction"]  = prediction.strip()[:300]
                data["prediction_updated_at"] = datetime.utcnow().isoformat()
                await storage.save(STORAGE_KEY.format(user_id=user_id), data)
                _slog("PREDICTIVE_UPDATED",
                      user=user_id,
                      pred=data["next_turn_prediction"][:80])
        except Exception as e:
            logger.debug("PREDICTIVE_UPDATE_ERROR user=%s err=%s", user_id, e)

    # ── Context hint per il prompt LLM ────────────────────────────────────────

    async def get_context_hint(self, user_id: str) -> str:
        """
        Ritorna un hint soft da iniettare nel contesto LLM.
        Vuoto durante shadow phase o se accuratezza insufficiente.
        """
        try:
            data    = await self._load(user_id)
            pred    = data.get("next_turn_prediction", "")
            total   = data.get("total_assessments", 0)
            history = data.get("accuracy_history", [])

            if not pred or total < SHADOW_TURNS:
                return ""

            avg_acc = sum(history) / len(history) if history else 0.0
            if avg_acc < MIN_ACCURACY:
                return ""

            hint = (
                f"[TENDENZA PREDITTIVA (accuratezza {avg_acc:.0%}): "
                f"basandomi sui pattern dell'utente, potrebbe voler approfondire: "
                f"{pred}]"
            )
            _slog("PREDICTIVE_HINT_INJECTED",
                  user=user_id,
                  acc=round(avg_acc, 3),
                  pred=pred[:80])
            return hint
        except Exception:
            return ""

    # ── Stats per debug / dashboard ───────────────────────────────────────────

    async def get_stats(self, user_id: str) -> dict:
        """Ritorna statistiche del motore predittivo per l'utente."""
        try:
            data    = await self._load(user_id)
            history = data.get("accuracy_history", [])
            avg     = sum(history) / len(history) if history else 0.0
            total   = data.get("total_assessments", 0)
            return {
                "total_assessments": total,
                "avg_accuracy":      round(avg, 3),
                "shadow_mode":       total < SHADOW_TURNS,
                "last_prediction":   data.get("next_turn_prediction", "")[:120],
                "last_surprise":     data.get("last_surprise_score"),
                "turns_to_active":   max(0, SHADOW_TURNS - total),
            }
        except Exception:
            return {}

    async def _load(self, user_id: str) -> dict:
        data = await storage.load(STORAGE_KEY.format(user_id=user_id), default={})
        return data if isinstance(data, dict) else {}


predictive_engine = PredictiveEngine()
