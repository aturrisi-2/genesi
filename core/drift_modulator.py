"""
DRIFT MODULATOR - Genesi Cognitive System v3
Modulazione probabilistica del tono di risposta.
Nessuna soglia statica. Combinazioni ponderate + variazione controllata.
Zero chiamate LLM. Opera sulla risposta base gia' generata.
"""

import logging
import math
import random
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)

DRIFT_CENTER = 0.5          # valore centrale neutro
DRIFT_RECENTERING_RATE = 0.01  # quanto si avvicina al centro ad ogni messaggio


def _sigmoid(x: float, center: float = 0.5, steepness: float = 6.0) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * (x - center)))


def _weighted_blend(*pairs) -> float:
    """Calcola media ponderata da coppie (weight, value)."""
    total_w = sum(w for w, _ in pairs)
    if total_w == 0:
        return 0.5
    return sum(w * v for w, v in pairs) / total_w


class DriftModulator:
    """
    Modula stile della risposta basandosi su latent_state + relational_state.
    Nessun if statico. Tutto e' combinazione continua.
    Introduce variazione probabilistica controllata.
    """

    def modulate_response_style(
        self,
        latent_state: Dict[str, float],
        relational_state: Dict[str, Any],
        base_response: str
    ) -> str:
        """
        Modula la risposta base.
        Non riscrive — trasforma strutturalmente in modo coerente.

        Influenza:
        - lunghezza frase
        - livello evocativo
        - profondita'
        - riferimento memoria
        - temperatura linguistica
        """
        if not base_response or len(base_response) < 5:
            return base_response

        # ── Compute modulation vector ──────────────────────────
        att = latent_state.get("attachment", 0.45)
        cur = latent_state.get("curiosity", 0.50)
        res = latent_state.get("emotional_resonance", 0.40)
        stb = latent_state.get("stability", 0.55)
        eng = latent_state.get("relational_energy", 0.45)

        trust = relational_state.get("trust", 0.2)
        depth = relational_state.get("depth", 0.1)
        stage = relational_state.get("stage", "initial")

        # ── Modulation scores (0-1 continuous) ─────────────────
        # Warmth: how warm/intimate the tone should be
        warmth = _weighted_blend(
            (0.30, _sigmoid(att, 0.5)),
            (0.25, _sigmoid(res, 0.45)),
            (0.20, _sigmoid(trust, 0.35)),
            (0.15, _sigmoid(eng, 0.4)),
            (0.10, _sigmoid(depth, 0.3))
        )

        # Expansiveness: tendency to elaborate
        expansiveness = _weighted_blend(
            (0.30, _sigmoid(cur, 0.5)),
            (0.25, _sigmoid(eng, 0.45)),
            (0.20, _sigmoid(depth, 0.35)),
            (0.15, _sigmoid(res, 0.4)),
            (0.10, _sigmoid(att, 0.4))
        )

        # Evocativeness: poetic/reflective quality
        evocativeness = _weighted_blend(
            (0.35, _sigmoid(res, 0.5)),
            (0.25, _sigmoid(att, 0.5)),
            (0.20, _sigmoid(stb, 0.5)),
            (0.20, _sigmoid(depth, 0.4))
        )

        # Groundedness: how anchored/concrete vs abstract
        groundedness = _weighted_blend(
            (0.40, _sigmoid(stb, 0.45)),
            (0.30, 1.0 - _sigmoid(res, 0.6)),
            (0.30, _sigmoid(trust, 0.3))
        )

        # ── Controlled probabilistic jitter ────────────────────
        # Small random variation so same state doesn't always produce same modulation
        warmth += random.gauss(0, 0.04)
        expansiveness += random.gauss(0, 0.04)
        evocativeness += random.gauss(0, 0.04)
        groundedness += random.gauss(0, 0.03)

        warmth = max(0.0, min(1.0, warmth))
        expansiveness = max(0.0, min(1.0, expansiveness))
        evocativeness = max(0.0, min(1.0, evocativeness))
        groundedness = max(0.0, min(1.0, groundedness))

        # ── Apply modulations ──────────────────────────────────
        result = base_response

        # 1. Warmth suffix — probabilistic warm closing
        result = self._apply_warmth(result, warmth)

        # 2. Expansiveness — extend or contract
        result = self._apply_expansiveness(result, expansiveness)

        # 3. Evocativeness — reflective additions
        result = self._apply_evocativeness(result, evocativeness, groundedness)

        # 4. Linguistic temperature — word-level variation
        result = self._apply_linguistic_temperature(result, warmth, evocativeness)
        
        # 5. Apply recentering towards center
        result = self._apply_recentering_to_result(result, warmth, expansiveness, evocativeness, groundedness)

        logger.info(
            "DRIFT_APPLIED warmth=%.3f expand=%.3f evoc=%.3f ground=%.3f len_delta=%+d",
            warmth, expansiveness, evocativeness, groundedness,
            len(result) - len(base_response)
        )

        return result
    
    def _apply_recentering_to_result(self, text: str, warmth: float, expansiveness: float, evocativeness: float, groundedness: float) -> str:
        """Applica recentering ai valori di drift dopo l'applicazione."""
        # Non modifichiamo il testo, ma registriamo il recentering per debug
        recentered_warmth = self._apply_recentering(warmth)
        recentered_expansiveness = self._apply_recentering(expansiveness)
        recentered_evocativeness = self._apply_recentering(evocativeness)
        recentered_groundedness = self._apply_recentering(groundedness)
        
        if any(abs(val - DRIFT_CENTER) > 0.01 for val in [warmth, expansiveness, evocativeness, groundedness]):
            logger.info(
                "DRIFT_RECENTERING warmth=%.3f->%.3f expand=%.3f->%.3f evoc=%.3f->%.3f ground=%.3f->%.3f",
                warmth, recentered_warmth, expansiveness, recentered_expansiveness,
                evocativeness, recentered_evocativeness, groundedness, recentered_groundedness
            )
        
        return text
    
    def _apply_recentering(self, current_value: float) -> float:
        """Spinge lentamente il valore verso il centro (0.5)."""
        if abs(current_value - DRIFT_CENTER) < 0.01:
            return current_value  # già abbastanza centrato
        
        direction = 1 if current_value < DRIFT_CENTER else -1
        new_value = current_value + (direction * DRIFT_RECENTERING_RATE)
        return max(0.0, min(1.0, new_value))

    # ── Modulation implementations ─────────────────────────────

    def _apply_warmth(self, text: str, warmth: float) -> str:
        """Aggiunge chiusura calda con probabilita' proporzionale a warmth."""
        # Probability of adding warm suffix scales with warmth
        p = _sigmoid(warmth, center=0.55, steepness=8.0) * 0.35
        if random.random() > p:
            return text

        # Don't add if text already ends with a warm phrase
        warm_endings = [
            " Sono qui.",
            " Ci sono.",
            " Sono con te.",
            " Ti ascolto.",
        ]
        text_lower = text.lower().rstrip(".")
        for ending in warm_endings:
            if text_lower.endswith(ending.lower().rstrip(".")):
                return text

        # Select suffix weighted by warmth level
        if warmth > 0.7:
            suffixes = [" Sono qui con te.", " Ci sono, sempre.", " Non sei solo."]
        elif warmth > 0.5:
            suffixes = [" Sono qui.", " Ci sono.", " Ti ascolto."]
        else:
            suffixes = [" Dimmi.", " Continua."]

        suffix = random.choice(suffixes)
        # Avoid repetition: don't add if last word of text matches first word of suffix
        if text.rstrip(".").split()[-1:] == suffix.strip().split()[:1]:
            return text

        # Fix: avoid double punctuation by ensuring proper spacing
        text_clean = text.rstrip(".")
        if suffix.startswith(" "):
            return text_clean + "." + suffix
        else:
            return text_clean + ". " + suffix

    def _apply_expansiveness(self, text: str, expansiveness: float) -> str:
        """Modula lunghezza: espande o contrae."""
        # High expansiveness + short text → add reflective bridge
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

        if expansiveness > 0.6 and len(sentences) == 1 and len(text) < 60:
            # Probabilistic expansion
            p = _sigmoid(expansiveness, center=0.6, steepness=8.0) * 0.30
            if random.random() < p:
                bridges = [
                    "Raccontami di piu'.",
                    "Dimmi cosa ti passa per la testa.",
                    "Cosa ti ha portato a pensarci?",
                    "C'e' qualcosa in particolare?",
                    "Vai avanti, ti ascolto."
                ]
                bridge = random.choice(bridges)
                # Avoid adding if bridge words already in text
                if bridge.split()[0].lower() not in text.lower():
                    return text.rstrip(".") + ". " + bridge

        # Low expansiveness + long text → trim to core (keep first 2 sentences)
        if expansiveness < 0.35 and len(sentences) > 2:
            p = _sigmoid(1.0 - expansiveness, center=0.6, steepness=6.0) * 0.25
            if random.random() < p:
                return " ".join(sentences[:2])

        return text

    def _apply_evocativeness(self, text: str, evocativeness: float,
                              groundedness: float) -> str:
        """Aggiunge qualita' riflessiva/evocativa."""
        # Only trigger with meaningful probability at high evocativeness + low groundedness
        p = _sigmoid(evocativeness, center=0.6, steepness=8.0) * \
            (1.0 - _sigmoid(groundedness, center=0.6, steepness=6.0)) * 0.20

        if random.random() > p:
            return text

        # Reflective insertions — context-free, universally applicable
        reflections = [
            "A volte le parole non bastano, ma il silenzio insieme vale molto.",
            "Quello che senti ha un peso reale.",
            "Non tutto deve avere una risposta immediata.",
            "Le cose importanti hanno bisogno di tempo.",
            "A volte basta sapere che qualcuno ascolta davvero.",
        ]

        reflection = random.choice(reflections)
        # Don't add if text already contains similar words
        reflection_key = reflection.split()[2:4]
        if any(w.lower() in text.lower() for w in reflection_key):
            return text

        return text + " " + reflection

    def _apply_linguistic_temperature(self, text: str, warmth: float,
                                       evocativeness: float) -> str:
        """Variazione a livello di parola — sostituzioni probabilistiche."""
        # Temperature = blend of warmth and evocativeness
        temp = _weighted_blend((0.6, warmth), (0.4, evocativeness))

        # Only apply at meaningful temperature levels
        if temp < 0.45:
            return text

        # Probabilistic word-level substitutions
        # Each substitution has its own probability scaled by temp
        substitutions = [
            ("sono qui", ["ci sono", "sono presente", "sono qui"]),
            ("ti ascolto", ["ti sento", "ti ascolto", "sono in ascolto"]),
            ("raccontami", ["dimmi", "parlami", "raccontami"]),
            ("capisco", ["comprendo", "sento", "capisco"]),
            ("dimmi", ["parlami", "raccontami", "dimmi"]),
        ]

        p_sub = _sigmoid(temp, center=0.55, steepness=6.0) * 0.25
        result = text

        for original, alternatives in substitutions:
            if original in result.lower() and random.random() < p_sub:
                # Pick a different alternative
                other = [a for a in alternatives if a != original]
                if other:
                    replacement = random.choice(other)
                    # Preserve case of first char
                    idx = result.lower().find(original)
                    if idx >= 0:
                        orig_segment = result[idx:idx + len(original)]
                        if orig_segment[0].isupper():
                            replacement = replacement[0].upper() + replacement[1:]
                        result = result[:idx] + replacement + result[idx + len(original):]
                    break  # max one substitution per pass

        return result


# Singleton
drift_modulator = DriftModulator()
