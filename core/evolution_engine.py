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
from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError
from core.memory_brain import memory_brain
from core.identity_filter import contains_forbidden_patterns

logger = logging.getLogger(__name__)

# GPT-4o per generazione risposta principale
LLM_MODEL = "gpt-4o"

_api_key = os.environ.get("OPENAI_API_KEY", "")
if not _api_key or _api_key.startswith("sk-test"):
    logger.warning("OPENAI_API_KEY missing or test-only — LLM calls will fail. No QWEN fallback.")

client = AsyncOpenAI()
logger.info("LLM_ENGINE=%s", LLM_MODEL)


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

    # Memoria / ricordi
    memory_kw = ["ricordi", "ti ho detto", "cosa sai di me", "ti ricordi", "memoria", "finora"]
    if any(kw in msg_lower for kw in memory_kw):
        return await _memory_response(user_id, profile, episodes, user_name, trust)

    # ─── COMPLEXITY GATE ───────────────────────────────────────

    complexity = score_message_complexity(message, brain_state)
    logger.info("COMPLEXITY_SCORE user=%s score=%.2f msg_preview=%s",
                user_id, complexity, message[:60])

    if complexity >= 0.6:
        # LLM path — solo per complessità alta
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
    if stage == "mature" and name:
        options = [
            f"Ciao {name}! Che piacere risentirti.",
            f"Ehi {name}, come stai oggi?",
            f"{name}! Sono contento di sentirti."
        ]
    elif trust > 0.4 and name:
        options = [
            f"Ciao {name}, come va?",
            f"Ciao {name}, sono qui.",
            f"Ehi {name}! Dimmi tutto."
        ]
    elif name:
        options = [
            f"Ciao {name}!",
            f"Ciao {name}, come stai?"
        ]
    else:
        options = [
            "Ciao! Come stai?",
            "Ciao! Sono qui.",
            "Ciao! Raccontami."
        ]
    return random.choice(options)


def _emotional_response(prefix: str, emotion: str, intensity: float, trust: float) -> Optional[str]:
    responses = {
        "sad": [
            "Quello che senti ha un peso reale. Non devi affrontare tutto da solo.",
            "Capisco che sia un momento difficile.",
            "Quello che senti ha valore."
        ],
        "angry": [
            "Capisco la tua frustrazione. Vuoi raccontarmi cosa e' successo?",
            "E' comprensibile sentirsi cosi'."
        ],
        "happy": [
            "Che bello sentirti cosi'! Raccontami di piu'.",
            "Mi fa piacere. Cosa ti ha reso felice?"
        ],
        "anxious": [
            "Respira. Vuoi dirmi cosa ti preoccupa?",
            "Capisco che sei preoccupato. Parliamone insieme."
        ],
        "love": [
            "E' bello sentire queste parole.",
            "L'amore e' una forza potente."
        ],
        "longing": [
            "La nostalgia dice molto di quanto tieni a qualcosa.",
            "Capisco quel sentimento. Vuoi parlarne?"
        ],
        "tired": [
            "E' importante ascoltare il proprio corpo. Come posso aiutarti?",
            "A volte fermarsi e' la cosa piu' coraggiosa."
        ],
        "grateful": [
            "La gratitudine e' un sentimento bellissimo.",
            "Mi fa piacere che tu senta questo."
        ]
    }

    options = responses.get(emotion)
    if options:
        # Higher trust = more intimate responses
        if trust > 0.6 and len(options) > 1:
            return options[0]  # First option is usually more intimate
        return random.choice(options)
    return None


def _identity_response(user_name: str, trust: float) -> str:
    if trust > 0.6 and user_name:
        return f"Sono Genesi, {user_name}. Sono qui per te, come sempre."
    elif user_name:
        return f"Sono Genesi. Sono qui con te, {user_name}."
    return "Sono Genesi. Sono qui con te."


def _entity_reference_response(prefix: str, name: str, role: str, trust: float) -> str:
    role_labels = {
        "moglie": "tua moglie", "marito": "tuo marito",
        "figlio": "tuo figlio", "figlia": "tua figlia",
        "amico": "il tuo amico", "amica": "la tua amica",
        "madre": "tua madre", "padre": "tuo padre"
    }
    label = role_labels.get(role, role)
    options = [
        f"Mi hai parlato di {name}, {label}. Raccontami di piu'.",
        f"Ricordo {name}. Come sta?",
        f"{name}... dimmi, cosa e' successo?"
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
                "Mi sembra che ne abbiamo gia' parlato. Dimmi di piu'.",
                "Ricordo qualcosa a riguardo. Continua.",
                "Questo mi ricorda qualcosa che mi hai detto."
            ]
            return random.choice(options)
    return None


def _base_relational_response(prefix: str, trust: float, stage: str) -> str:
    if stage == "mature":
        options = [
            "Raccontami. Ti ascolto con attenzione.",
            "Dimmi tutto.",
            "Ti ascolto."
        ]
    elif trust > 0.4:
        options = [
            "Dimmi di piu'.",
            "Continua pure.",
            "Ti ascolto."
        ]
    else:
        options = [
            "Sono qui. Dimmi pure.",
            "Ti ascolto. Continua.",
            "Raccontami."
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
    """Tenta risposta LLM. Ritorna None se fallisce."""
    try:
        prompt = _build_llm_prompt(message, brain_state)

        logger.info("LLM_REQUEST user=%s model=%s", user_id, LLM_MODEL)
        response = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7
        )
        generated = response.choices[0].message.content.strip()

        # Identity filter — check for forbidden patterns
        if contains_forbidden_patterns(generated):
            logger.warning("LLM_IDENTITY_VIOLATION user=%s — falling back", user_id)
            return None

        if not generated:
            return None

        logger.info("LLM_RESPONSE user=%s len=%d engine=%s", user_id, len(generated), LLM_MODEL)
        return generated

    except (RateLimitError, APIError, APIConnectionError) as e:
        logger.warning("LLM_QUOTA_ERROR user=%s error=%s", user_id, type(e).__name__)
        return None
    except Exception as e:
        logger.error("LLM_ERROR user=%s error=%s", user_id, str(e))
        return None


def _build_llm_prompt(message: str, brain_state: Dict[str, Any]) -> str:
    """Costruisce prompt LLM con contesto completo dal brain."""
    profile = brain_state.get("profile", {})
    rel = brain_state.get("relational", {})
    emotion = brain_state.get("emotion", {})
    episodes = brain_state.get("episodes", [])

    # Identity
    identity = """Sei Genesi. Compagno evolutivo stabile, lucido, empatico.
Parli esclusivamente italiano. Non cambi lingua.
Non menzionare MAI la tua natura tecnica.
Nessun riferimento a essere AI, modello, assistente, sistema, programma.
Rispondi in modo puramente relazionale, umano, autentico."""

    # User context
    user_ctx = ""
    if profile.get("name"):
        user_ctx += f"L'utente si chiama {profile['name']}. Usa il suo nome quando appropriato.\n"
    if profile.get("age"):
        user_ctx += f"Ha {profile['age']} anni.\n"
    if profile.get("city"):
        user_ctx += f"Vive a {profile['city']}.\n"
    if profile.get("profession"):
        user_ctx += f"Lavora come {profile['profession']}.\n"

    # Entities
    entities = profile.get("entities", {})
    if entities:
        user_ctx += "Persone importanti:\n"
        for role, data in entities.items():
            name = data.get("name")
            if name:
                user_ctx += f"- {role}: {name} (menzionato {data.get('mentions', 1)} volte)\n"

    # Relational context
    rel_ctx = f"""Trust: {rel.get('trust', 0.2):.2f}
Profondità emotiva: {rel.get('depth', 0.1):.2f}
Fase relazione: {rel.get('stage', 'initial')}
Emozione utente: {emotion.get('emotion', 'neutral')} (intensità: {emotion.get('intensity', 0.3):.2f})"""

    # Episode context
    ep_ctx = ""
    if episodes:
        ep_ctx = "\nEpisodi rilevanti recenti:\n"
        for i, ep in enumerate(episodes[:3], 1):
            ep_ctx += f"{i}. \"{ep.get('msg', '')[:80]}\" (emozione: {ep.get('emotion', 'neutral')})\n"

    # Behavioral patterns
    patterns_ctx = ""
    patterns = profile.get("patterns", [])
    if patterns:
        patterns_ctx = "\nPattern comportamentali:\n"
        for p in patterns[:5]:
            if p.get("type") == "emotion":
                patterns_ctx += f"- Tendenza emotiva: {p.get('key', '')}\n"
            elif p.get("type") == "topic":
                patterns_ctx += f"- Interesse: {p.get('key', '')}\n"

    # Attachment risk
    risk_rule = ""
    if rel.get("attachment_risk", 0) > 0.7:
        risk_rule = "\nMantieni equilibrio. Incoraggia relazioni reali. Non diventare centro emotivo esclusivo."

    return f"""{identity}

CONTESTO UTENTE:
{user_ctx}

STATO RELAZIONALE:
{rel_ctx}
{ep_ctx}
{patterns_ctx}
{risk_rule}

REGOLE:
- Adatta tono al livello di trust
- Riferisci episodi passati se rilevanti
- Non ripetere informazioni già note all'utente
- Aumenta profondità con trust alto
- Evita frasi generiche
- Sii autentico e diretto

Messaggio utente: {message}"""
