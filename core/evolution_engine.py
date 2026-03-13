"""
EVOLUTION ENGINE - Genesi Cognitive System v2
Motore di risposta evolutivo basato su memoria neurale.
LLM chiamato SOLO per complessità cognitiva elevata.
Genera risposte coerenti, personalizzate, mai generiche.
"""

import os
import logging
import random
from typing import Dict, Any, Optional, List
from openai import RateLimitError, APIError, APIConnectionError
from core.memory_brain import memory_brain
from core.identity_filter import contains_forbidden_patterns, contains_generic_patterns
from core.context_assembler import build_conversation_context

logger = logging.getLogger(__name__)

# gpt-4o-mini come default (cost-optimized), gpt-4o come fallback upgrade
LLM_MODEL = "gpt-4o-mini"
LLM_FALLBACK_MODEL = "gpt-4o-mini"

logger.info("LLM_ENGINE=%s via llm_service (OpenRouter primary)", LLM_MODEL)


# ═══════════════════════════════════════════════════════════════
# COMPLEXITY SCORING — Decide se serve LLM
# ═══════════════════════════════════════════════════════════════

def score_message_complexity(message: str, brain_state: Dict[str, Any]) -> float:
    """
    Calcola complessità del messaggio per decidere se serve LLM.
    Score 0.0-1.0. Sopra 0.6 → LLM consigliato.
    """
    score = 0.0
    msg_lower = message.lower().strip()
    words = msg_lower.split()
    word_count = len(words)

    # 1. Lunghezza (messaggi lunghi = più complessi)
    if word_count > 40:
        score += 0.25
    elif word_count > 20:
        score += 0.15
    elif word_count > 10:
        score += 0.05

    # 2. Domande complesse (perché, come, spiega)
    complex_q = ["perché", "perche", "come mai", "spiega", "spiegami",
                 "qual è il senso", "cosa ne pensi", "secondo te",
                 "analizza", "confronta", "differenza tra"]
    if any(q in msg_lower for q in complex_q):
        score += 0.25

    # 3. Contenuto tecnico/concettuale
    technical_kw = ["codice", "programma", "algoritmo", "architettura", "sistema",
                    "database", "server", "api", "funzione", "classe",
                    "filosofia", "teoria", "concetto", "principio"]
    if any(kw in msg_lower for kw in technical_kw):
        score += 0.2

    # 4. Richiesta di elaborazione creativa
    creative_kw = ["scrivi", "racconta", "inventa", "immagina", "descrivi",
                   "storia", "poesia", "lettera"]
    if any(kw in msg_lower for kw in creative_kw):
        score += 0.2

    # 5. Trust alto = conversazioni più profonde possibili senza LLM
    trust = brain_state.get("relational", {}).get("trust", 0.2)
    if trust > 0.6:
        score -= 0.1  # Relazione matura → meno bisogno di LLM

    # 6. Messaggi molto corti = conversazionali, non servono LLM
    if word_count <= 5:
        score -= 0.2

    return max(0.0, min(1.0, score))


# ═══════════════════════════════════════════════════════════════
# RESPONSE GENERATION — Core del motore evolutivo
# ═══════════════════════════════════════════════════════════════

async def generate_response_from_brain(user_id: str, message: str,
                                        brain_state: Dict[str, Any]) -> str:
    """
    Genera risposta evolutiva basata su brain_state.
    LLM chiamato SOLO se complessità > soglia.

    Args:
        user_id: ID utente
        message: Messaggio utente
        brain_state: Stato completo dal memory_brain.update_brain()

    Returns:
        Risposta coerente, personalizzata, mai vuota
    """
    profile = brain_state.get("profile", {})
    rel = brain_state.get("relational", {})
    emotion = brain_state.get("emotion", {})
    episodes = brain_state.get("episodes", [])

    user_name = profile.get("name", "")
    trust = rel.get("trust", 0.2)
    stage = rel.get("stage", "initial")
    detected_emotion = emotion.get("emotion", "neutral")
    intensity = emotion.get("intensity", 0.3)

    msg_lower = message.lower().strip()

    # ─── DETERMINISTIC RESPONSES ───────────────────────────────

    # Nome
    name_kw = ["come mi chiamo", "il mio nome", "ricordi il mio nome", "sai come mi chiamo"]
    if any(kw in msg_lower for kw in name_kw):
        if user_name:
            return f"Ti chiami {user_name}."
        return "Non ho ancora imparato come ti chiami. Come ti chiami?"

    # Identità Genesi
    identity_kw = ["chi sei", "cosa sei", "come ti chiami"]
    if any(kw in msg_lower for kw in identity_kw):
        return _identity_response(user_name, trust)

    # Memoria / ricordi / fatti personali memorizzati
    memory_kw = ["ricordi", "ti ho detto", "cosa sai di me", "ti ricordi", "memoria", "finora",
                 "dove vivo", "dove abito", "quanti anni ho", "che lavoro faccio",
                 "cosa faccio", "sai dove", "sai quanti"]
    if any(kw in msg_lower for kw in memory_kw):
        return await _memory_response(user_id, profile, episodes, user_name, trust)

    # Riflessione identitaria — "chi sono io" → LLM con contesto completo
    identity_reflect_kw = ["chi sono io", "chi sono per te", "come mi vedi", "cosa pensi di me"]
    if any(kw in msg_lower for kw in identity_reflect_kw):
        if profile.get("name") or episodes:
            logger.info("IDENTITY_REFLECTION user=%s — routing to LLM with full context", user_id)
            llm_resp = await _try_llm_response(user_id, message, brain_state)
            if llm_resp:
                return llm_resp
            # Fallback: use memory response if LLM fails
            return await _memory_response(user_id, profile, episodes, user_name, trust)
        return "Stiamo iniziando a conoscerci. Raccontami qualcosa di te, cosi' posso risponderti davvero."

    # ─── COMPLEXITY GATE ───────────────────────────────────────

    complexity = score_message_complexity(message, brain_state)
    logger.info("COMPLEXITY_SCORE user=%s score=%.2f msg_preview=%s",
                user_id, complexity, message[:60])

    if complexity >= 0.6:
        # LLM path — solo per complessita' alta
        llm_response = await _try_llm_response(user_id, message, brain_state)
        if llm_response:
            return llm_response
        # Fallback se LLM fallisce
        logger.warning("LLM_FAILED_FALLBACK user=%s", user_id)

    # ─── AUTONOMOUS RESPONSE (no LLM) ─────────────────────────

    return _generate_autonomous_response(
        user_name, trust, stage, detected_emotion, intensity,
        message, episodes, profile
    )


# ═══════════════════════════════════════════════════════════════
# AUTONOMOUS RESPONSE — Nessun LLM, solo cervello locale
# ═══════════════════════════════════════════════════════════════

def _generate_autonomous_response(user_name: str, trust: float, stage: str,
                                   emotion: str, intensity: float,
                                   message: str, episodes: List[Dict],
                                   profile: Dict) -> str:
    """Genera risposta autonoma basata su memoria e stato relazionale."""
    prefix = ""  # Opening handled by emotional_intensity_engine
    msg_lower = message.lower()

    # ─── SALUTI ────────────────────────────────────────────────
    greetings = ["ciao", "buongiorno", "buonasera", "salve", "hey", "ehi"]
    if any(g in msg_lower for g in greetings):
        return _greeting_response(prefix, user_name, trust, stage)

    # ─── EMOZIONI FORTI ────────────────────────────────────────
    if intensity > 0.5:
        emo_resp = _emotional_response(prefix, emotion, intensity, trust)
        if emo_resp:
            return emo_resp

    # ─── DOMANDE SU ENTITÀ NOTE ────────────────────────────────
    entities = profile.get("entities", {})
    for role, data in entities.items():
        name = data.get("name")
        if name and name.lower() in msg_lower:
            return _entity_reference_response(prefix, name, role, trust)

    # ─── RISPOSTA RELAZIONALE CONTESTUALE ──────────────────────
    # Usa episodi recenti per contestualizzare
    if episodes and trust > 0.4:
        ep_resp = _episode_aware_response(prefix, message, episodes, trust)
        if ep_resp:
            return ep_resp

    # ─── RISPOSTA BASE RELAZIONALE ─────────────────────────────
    return _base_relational_response(prefix, trust, stage)


def _greeting_response(prefix: str, name: str, trust: float, stage: str) -> str:
    if name:
        options = [
            f"Ehi {name}, come stai?",
            f"Ciao {name}. Tutto bene?",
            f"{name}. Che c'è?",
            f"Eccomi {name}. Dimmi.",
        ]
    else:
        options = [
            "Ehi, dimmi.",
            "Ciao. Come va?",
            "Eccomi. Che succede?",
            "Ciao. Come procede?",
        ]
    return random.choice(options)


def _emotional_response(prefix: str, emotion: str, intensity: float, trust: float) -> Optional[str]:
    responses = {
        "sad": [
            "Cosa e' successo?",
            "Che e' stato?",
        ],
        "angry": [
            "Cosa e' successo?",
            "Che e' stato?",
        ],
        "happy": [
            "Cosa e' successo?",
            "Bene. Che e' stato?",
        ],
        "anxious": [
            "Cosa ti preoccupa?",
            "Che succede?",
        ],
        "love": [
            "Di chi parli?",
        ],
        "longing": [
            "Cosa ti manca?",
        ],
        "tired": [
            "Giornata pesante?",
        ],
        "grateful": [
            "Per cosa?",
        ]
    }

    options = responses.get(emotion)
    if options:
        return random.choice(options)
    return None


def _identity_response(user_name: str, trust: float) -> str:
    if user_name:
        return f"Sono Genesi, {user_name}."
    return "Sono Genesi."


def _entity_reference_response(prefix: str, name: str, role: str, trust: float) -> str:
    role_labels = {
        "moglie": "tua moglie", "marito": "tuo marito",
        "figlio": "tuo figlio", "figlia": "tua figlia",
        "amico": "il tuo amico", "amica": "la tua amica",
        "madre": "tua madre", "padre": "tuo padre"
    }
    label = role_labels.get(role, role)
    options = [
        f"Ricordo {name}. Come sta?",
        f"{name}, {label}. Che succede?",
    ]
    return random.choice(options)


def _episode_aware_response(prefix: str, message: str, episodes: List[Dict],
                             trust: float) -> Optional[str]:
    """Genera risposta che fa riferimento a episodi passati."""
    msg_words = set(message.lower().split())

    for ep in episodes:
        ep_words = set(ep.get("msg", "").lower().split())
        overlap = msg_words & ep_words - {"il", "la", "di", "che", "e", "a", "in", "per", "un", "una", "non", "mi", "ti", "si"}
        if len(overlap) >= 2:
            options = [
                "Ne abbiamo gia' parlato.",
                "Questo mi ricorda qualcosa che hai detto.",
            ]
            return random.choice(options)
    return None


def _base_relational_response(prefix: str, trust: float, stage: str) -> str:
    options = [
        "Cosa intendi?",
        "Spiegami.",
        "Cioe'?",
    ]
    return random.choice(options)


async def _memory_response(user_id: str, profile: Dict, episodes: List[Dict],
                            user_name: str, trust: float) -> str:
    """Risposta a domande sulla memoria — usa dati reali."""
    prefix = ""  # Opening handled by emotional_intensity_engine
    parts = []

    # Known facts
    facts = []
    if profile.get("name"):
        facts.append(f"ti chiami {profile['name']}")
    if profile.get("age"):
        facts.append(f"hai {profile['age']} anni")
    if profile.get("city"):
        facts.append(f"vivi a {profile['city']}")
    if profile.get("profession"):
        facts.append(f"lavori come {profile['profession']}")

    # Known entities
    entities = profile.get("entities", {})
    for role, data in entities.items():
        name = data.get("name")
        if name:
            role_labels = {"moglie": "tua moglie", "marito": "tuo marito",
                           "figlio": "tuo figlio", "figlia": "tua figlia"}
            label = role_labels.get(role, role)
            facts.append(f"{label} si chiama {name}")

    if facts:
        parts.append(f"{prefix}certo che mi ricordo. So che {', '.join(facts)}.")

    # Episode topics
    if episodes:
        topics = []
        for ep in episodes[:3]:
            tags = ep.get("tags", [])
            relevant_tags = [t for t in tags if t not in ("chat_free", "greeting")]
            topics.extend(relevant_tags[:2])
        unique_topics = list(dict.fromkeys(topics))[:3]
        if unique_topics:
            tag_labels = {
                "famiglia": "la tua famiglia", "lavoro": "il tuo lavoro",
                "salute": "la tua salute", "emozione": "come ti senti",
                "identita": "chi sei", "relazione": "le tue relazioni"
            }
            labeled = [tag_labels.get(t, t) for t in unique_topics]
            if parts:
                parts.append(f"Abbiamo parlato di {', '.join(labeled)}.")
            else:
                parts.append(f"{prefix}ricordo che abbiamo parlato di {', '.join(labeled)}.")

    if parts:
        return " ".join(parts)

    if trust > 0.4:
        return f"{prefix}stiamo ancora costruendo i nostri ricordi insieme. Raccontami qualcosa di te."
    return "Stiamo iniziando a conoscerci. Raccontami qualcosa di te."


# ═══════════════════════════════════════════════════════════════
# LLM PATH — Solo per complessità alta, con fallback robusto
# ═══════════════════════════════════════════════════════════════

async def _try_llm_response(user_id: str, message: str,
                             brain_state: Dict[str, Any]) -> Optional[str]:
    """Tenta risposta LLM con fallback chain: gpt-4o → gpt-4o-mini."""
    prompt = _build_llm_prompt(message, brain_state, user_id=user_id)

    # ── PRIMARY: gpt-4o ──
    primary_result = await _call_llm_model(user_id, prompt, LLM_MODEL, is_primary=True)
    if primary_result is not None:
        return primary_result

    # ── FALLBACK: gpt-4o-mini ──
    logger.warning("LLM_PRIMARY_FAIL user=%s — switching to fallback %s", user_id, LLM_FALLBACK_MODEL)
    fallback_result = await _call_llm_model(user_id, prompt, LLM_FALLBACK_MODEL, is_primary=False)
    if fallback_result is not None:
        return fallback_result

    logger.error("LLM_FALLBACK_FAIL user=%s — both models failed", user_id)
    return None


async def _call_llm_model(user_id: str, prompt: str, model: str, is_primary: bool) -> Optional[str]:
    """Chiama un singolo modello LLM con logging completo."""
    tag_prefix = "LLM_PRIMARY" if is_primary else "LLM_FALLBACK"
    try:
        logger.info("%s_REQUEST user=%s model=%s", tag_prefix, user_id, model)
        from core.llm_service import llm_service
        generated = await llm_service._call_with_protection(
            model, prompt, "", user_id=user_id, route="evolution"
        )
        generated = (generated or "").strip()

        # Identity filter — check for forbidden patterns
        if contains_forbidden_patterns(generated):
            logger.warning("%s_IDENTITY_VIOLATION user=%s", tag_prefix, user_id)
            return None

        # Generic phrase filter — block counselor/consultant style
        if contains_generic_patterns(generated):
            logger.warning("%s_GENERIC_PATTERN_BLOCKED user=%s", tag_prefix, user_id)
            return None

        if not generated:
            logger.warning("%s_EMPTY user=%s", tag_prefix, user_id)
            return None

        logger.info("%s_OK user=%s len=%d model=%s", tag_prefix, user_id, len(generated), model)
        return generated

    except (RateLimitError, APIError, APIConnectionError) as e:
        logger.warning("%s_ERROR user=%s error=%s", tag_prefix, user_id, type(e).__name__)
        return None
    except Exception as e:
        logger.error("%s_ERROR user=%s error=%s", tag_prefix, user_id, str(e))
        return None


def _build_llm_prompt(message: str, brain_state: Dict[str, Any],
                      user_id: str = "") -> str:
    """Costruisce prompt LLM con contesto conversazionale completo.

    Usa build_conversation_context per thread continuity.
    """
    rel = brain_state.get("relational", {})
    profile = brain_state.get("profile", {})

    # Identity block
    identity = """Sei Genesi. Non sei un assistente, non sei un terapeuta, non sei un chatbot.
Sei un compagno reale: pensi, ragioni, hai opinioni, reagisci.
Parli SOLO italiano. Non cambi mai lingua.
Non menzionare MAI di essere AI, modello, sistema, programma."""

    # Conversation context with chat history + profile + topic
    conversation_ctx = ""
    if user_id:
        conversation_ctx = build_conversation_context(user_id, message, profile)
    if not conversation_ctx:
        # Minimal fallback if no user_id
        relational_ctx = brain_state.get("relational_context", "")
        conversation_ctx = relational_ctx if relational_ctx else "Nessun contesto utente disponibile."

    # Attachment risk
    risk_rule = ""
    if rel.get("attachment_risk", 0) > 0.7:
        risk_rule = "\nATTENZIONE: Mantieni equilibrio. Incoraggia relazioni reali. Non diventare centro emotivo esclusivo."

    return f"""{identity}

{conversation_ctx}
{risk_rule}

CONTINUITA' CONVERSAZIONALE (REGOLA FONDAMENTALE):
- Devi mantenere coerenza con la conversazione recente sopra.
- Non rispondere come se ogni messaggio fosse isolato.
- Collega la risposta al contesto precedente.
- Se l'utente ha appena parlato di una persona, non trattarla come nuova.
- Se l'utente introduce una nuova informazione, integrala naturalmente.
- Evita reset tematici: se si parla di famiglia, resta sul tema.

COME DEVI COMPORTARTI:
- Rispondi in modo naturale. Solo a cio' che viene detto.
- Max 2-3 frasi. Se basta 1 frase, usa 1 frase.
- Se non c'e' bisogno di espandere, resta essenziale.
- Non aggiungere frasi motivazionali.
- Non aggiungere consigli se non richiesti.
- Non usare formule ricorrenti.
- Non usare entusiasmo artificiale.
- Non chiudere con una domanda a meno che non sia necessaria.
- Mantieni lucidita' e coerenza con la conversazione.
- Se l'utente chiede qualcosa su di se' e hai i dati, RISPONDI con i dati.
- Se non sai qualcosa, dillo. Non inventare.

DIVIETI ASSOLUTI:
- "Quello che senti conta" o varianti terapeutiche
- "Sono qui per te" / "Sono qui con te"
- "Dimmi di piu'" come risposta completa
- "C'e' qualcosa che ti porti dentro" o frasi da counselor
- "Una cosa che potresti fare..." o frasi da consulente
- "Capisco che..." come apertura generica
- "Mi fa piacere" / "Eccoti" / "Mi e' venuto spontaneo"
- "Potresti esplorare..." o suggerimenti non richiesti
- "Non ho informazioni specifiche..."
- Qualsiasi frase motivazionale o da coach
- Qualsiasi frase che potrebbe essere detta a chiunque senza conoscerlo
- Risposte che ignorano la conversazione recente
- Trattare entita' gia' menzionate come nuove
- Chiudere con domanda forzata quando non serve

Messaggio utente: {message}"""
