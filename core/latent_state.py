"""
LATENT STATE ENGINE - Genesi Cognitive System v3
Vettore latente dinamico a 5 dimensioni.
Aggiornato ad ogni messaggio. Zero chiamate LLM.
Persistente con decay su inattivita'.
"""

import logging
import math
import random
from datetime import datetime
from typing import Dict, Any
from core.storage import storage

logger = logging.getLogger(__name__)

STORAGE_KEY = "latent_state:{user_id}"

# Decay rates per hour of inactivity
DECAY_RATES = {
    "attachment": 0.002,           # lento
    "curiosity": 0.008,            # medio
    "emotional_resonance": 0.006,  # medio
    "stability": 0.001,            # lento
    "relational_energy": 0.015     # rapido
}

# Neutral equilibrium values — state drifts toward these on inactivity
EQUILIBRIUM = {
    "attachment": 0.45,
    "curiosity": 0.50,
    "emotional_resonance": 0.40,
    "stability": 0.55,
    "relational_energy": 0.45
}


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def _sigmoid_delta(x: float, center: float = 0.5, steepness: float = 6.0) -> float:
    """Sigmoid-shaped activation: returns 0-1 value centered around `center`.
    Used to produce smooth, non-linear influence curves instead of if-thresholds."""
    return 1.0 / (1.0 + math.exp(-steepness * (x - center)))


class LatentStateEngine:
    """
    Vettore latente dinamico a 5 dimensioni.
    Ogni dimensione evolve in modo continuo, non discreto.
    Nessuna soglia statica. Combinazioni ponderate + sigmoid activation.
    """

    def _default_state(self) -> Dict[str, Any]:
        return {
            "attachment": 0.45,
            "curiosity": 0.50,
            "emotional_resonance": 0.40,
            "stability": 0.55,
            "relational_energy": 0.45,
            "last_update": datetime.now().isoformat(),
            "update_count": 0
        }

    async def load(self, user_id: str) -> Dict[str, Any]:
        key = STORAGE_KEY.replace("{user_id}", user_id)
        state = await storage.load(key, default=None)
        if state and isinstance(state, dict) and "attachment" in state:
            return state
        state = self._default_state()
        await self._save(user_id, state)
        return state

    async def _save(self, user_id: str, state: Dict[str, Any]) -> None:
        key = STORAGE_KEY.replace("{user_id}", user_id)
        await storage.save(key, state)

    def _apply_inactivity_decay(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Decay verso equilibrio proporzionale alle ore di inattivita'."""
        last_str = state.get("last_update")
        if not last_str:
            return state
        try:
            last = datetime.fromisoformat(last_str)
        except (ValueError, TypeError):
            return state

        hours_inactive = max(0.0, (datetime.now() - last).total_seconds() / 3600.0)
        if hours_inactive < 0.5:
            return state  # meno di 30 min — nessun decay

        for dim, rate in DECAY_RATES.items():
            current = state.get(dim, EQUILIBRIUM[dim])
            eq = EQUILIBRIUM[dim]
            decay_amount = rate * hours_inactive
            if current > eq:
                state[dim] = _clamp(current - decay_amount)
            elif current < eq:
                state[dim] = _clamp(current + decay_amount)
            # Snap to equilibrium if close enough
            if abs(state[dim] - eq) < 0.01:
                state[dim] = eq

        return state

    async def update_latent_state(
        self,
        user_id: str,
        user_message: str,
        emotional_analysis: Dict[str, Any],
        relational_state: Dict[str, Any],
        episode_stored: bool = False,
        episode_tags: list = None
    ) -> Dict[str, Any]:
        """
        Aggiorna vettore latente basandosi su segnali multipli.
        Zero LLM. Combinazioni ponderate con sigmoid activation.
        """
        state = await self.load(user_id)
        state = self._apply_inactivity_decay(state)

        # ── Signal extraction ──────────────────────────────────
        emotion = emotional_analysis.get("emotion", "neutral")
        intensity = emotional_analysis.get("intensity", 0.3)
        vulnerability = emotional_analysis.get("vulnerability", 0.0)
        urgency = emotional_analysis.get("urgency", 0.0)

        trust = relational_state.get("trust", 0.2)
        depth = relational_state.get("depth", 0.1)
        consistency = relational_state.get("consistency", 0.5)
        total_msgs = relational_state.get("history", {}).get("total_msgs", 0)

        msg_len = len(user_message)
        msg_words = len(user_message.split())
        has_question = "?" in user_message
        msg_lower = user_message.lower()

        # Thematic repetition signal: how many tags overlap with recent
        tags = episode_tags or []
        tag_repetition = min(1.0, len(tags) * 0.2)  # more tags = more thematic density

        # Conversational depth signal: combination of trust, message substance, emotion
        conv_depth = _sigmoid_delta(
            0.3 * trust + 0.3 * (min(msg_len, 200) / 200.0) + 0.2 * intensity + 0.2 * depth,
            center=0.4
        )

        # ── ATTACHMENT ─────────────────────────────────────────
        # Grows with vulnerability, personal sharing, trust momentum
        personal_kw = ["chiamo", "nome", "famiglia", "moglie", "marito", "figlio",
                       "figlia", "lavoro", "vivo", "abito", "anni", "amo", "paura",
                       "soffro", "piango", "solo", "solitudine"]
        personal_signal = _sigmoid_delta(
            sum(1 for kw in personal_kw if kw in msg_lower) / 3.0,
            center=0.3, steepness=4.0
        )
        attachment_delta = (
            0.30 * _sigmoid_delta(vulnerability, center=0.4) +
            0.25 * personal_signal +
            0.20 * _sigmoid_delta(trust, center=0.3) +
            0.15 * _sigmoid_delta(intensity, center=0.5) +
            0.10 * tag_repetition
        )
        # Scale: raw delta is 0-1, we want small increments
        attachment_delta = (attachment_delta - 0.5) * 0.06
        state["attachment"] = _clamp(state["attachment"] + attachment_delta)

        # ── CURIOSITY ──────────────────────────────────────────
        # Grows with questions, longer messages, novel topics
        question_kw = ["perche", "perché", "come", "cosa", "quando", "dove",
                       "chi", "quale", "quanto", "dimmi", "spiegami", "raccontami"]
        question_signal = _sigmoid_delta(
            (1.0 if has_question else 0.0) +
            sum(0.3 for kw in question_kw if kw in msg_lower),
            center=0.5, steepness=4.0
        )
        novelty_signal = 1.0 - tag_repetition  # new topics = high novelty
        curiosity_delta = (
            0.40 * question_signal +
            0.25 * novelty_signal +
            0.20 * _sigmoid_delta(msg_words / 20.0, center=0.4) +
            0.15 * (1.0 - consistency)  # varied emotions = more curiosity
        )
        curiosity_delta = (curiosity_delta - 0.5) * 0.05
        state["curiosity"] = _clamp(state["curiosity"] + curiosity_delta)

        # ── EMOTIONAL RESONANCE ────────────────────────────────
        # Grows with emotional intensity, vulnerability, non-neutral emotions
        is_emotional = 1.0 if emotion != "neutral" else 0.0
        resonance_delta = (
            0.35 * _sigmoid_delta(intensity, center=0.4) +
            0.25 * _sigmoid_delta(vulnerability, center=0.3) +
            0.20 * is_emotional +
            0.10 * _sigmoid_delta(urgency, center=0.3) +
            0.10 * _sigmoid_delta(depth, center=0.3)
        )
        resonance_delta = (resonance_delta - 0.5) * 0.07
        state["emotional_resonance"] = _clamp(state["emotional_resonance"] + resonance_delta)

        # ── STABILITY ──────────────────────────────────────────
        # Grows with consistency, regular interaction, trust
        # Decreases with high variance, emotional swings
        variance = relational_state.get("history", {}).get("emotion_variance", 0.0)
        interaction_regularity = _sigmoid_delta(
            min(total_msgs, 50) / 50.0,
            center=0.2, steepness=5.0
        )
        stability_delta = (
            0.30 * _sigmoid_delta(consistency, center=0.4) +
            0.25 * interaction_regularity +
            0.25 * _sigmoid_delta(trust, center=0.3) +
            0.20 * (1.0 - _sigmoid_delta(variance, center=0.05, steepness=20.0))
        )
        stability_delta = (stability_delta - 0.5) * 0.04
        state["stability"] = _clamp(state["stability"] + stability_delta)

        # ── RELATIONAL ENERGY ──────────────────────────────────
        # Immediate energy of the interaction. Spikes and fades fast.
        energy_delta = (
            0.25 * _sigmoid_delta(intensity, center=0.3) +
            0.20 * _sigmoid_delta(msg_words / 15.0, center=0.4) +
            0.20 * (1.0 if episode_stored else 0.3) +
            0.20 * _sigmoid_delta(trust, center=0.3) +
            0.15 * conv_depth
        )
        energy_delta = (energy_delta - 0.45) * 0.08
        state["relational_energy"] = _clamp(state["relational_energy"] + energy_delta)

        # ── Micro-noise for non-determinism ────────────────────
        # Tiny controlled jitter so identical inputs don't produce identical states
        for dim in DECAY_RATES:
            noise = random.gauss(0, 0.003)
            state[dim] = _clamp(state[dim] + noise)

        # ── Persist ────────────────────────────────────────────
        state["last_update"] = datetime.now().isoformat()
        state["update_count"] = state.get("update_count", 0) + 1
        await self._save(user_id, state)

        logger.info(
            "LATENT_STATE_UPDATE user=%s att=%.3f cur=%.3f res=%.3f stb=%.3f eng=%.3f n=%d",
            user_id,
            state["attachment"], state["curiosity"],
            state["emotional_resonance"], state["stability"],
            state["relational_energy"], state["update_count"]
        )

        return state

    def get_vector(self, state: Dict[str, Any]) -> Dict[str, float]:
        """Restituisce solo le 5 dimensioni come dict pulito."""
        return {
            "attachment": state.get("attachment", 0.45),
            "curiosity": state.get("curiosity", 0.50),
            "emotional_resonance": state.get("emotional_resonance", 0.40),
            "stability": state.get("stability", 0.55),
            "relational_energy": state.get("relational_energy", 0.45)
        }


# Singleton
latent_state_engine = LatentStateEngine()
