"""
RESPONSE FILTER - Genesi Core
Filtro post-generazione finale. Blocca template residui, loop risposte identiche,
frasi meta-meccaniche. Agisce DOPO la generazione LLM, PRIMA del return.
"""

import re
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# BLACKLIST — frasi template residue da rimuovere
# ═══════════════════════════════════════════════════════════════

TEMPLATE_BLACKLIST = [
    # Coach / counselor
    r"capisco,",
    r"^va bene,",
    r"se hai qualcosa",
    r"sono qui\.",
    r"^sono qui$",
    r"non ho abbastanza informazioni",
    r"non sono programmato",
    r"non posso esprimere opinioni",
    r"non seguo uno schema fisso",
    # Meta-mechanical (FASE 6)
    r"sono programmato",
    r"non ho opinioni",
    r"non ho accesso",
    r"come intelligenza artificiale",
    r"in quanto ai",
    r"in quanto intelligenza",
    r"come modello linguistico",
    r"come modello di linguaggio",
    r"non sono in grado di provare",
    r"non provo emozioni",
    r"non ho sentimenti",
    # Leaked template phrases
    r"mi fa piacere sapere",
    r"assistente virtuale",
    r"assistente informativo",
    r"se vuoi parlare di qualcosa",
    r"se vuoi semplicemente parlare",
    r"puoi fornire pi[uù] contesto",
    r"non ho la possibilit[aà] di",
    r"spero che possiate",
    r"se hai una domanda specifica",
    r"non ho informazioni sufficienti",
    # Motivational / coaching
    r"ricorda che sei",
    r"non dimenticare che",
    r"il primo passo",
    r"un passo alla volta",
    r"ogni giorno e' un",
    r"ogni giorno è un",
    r"ce la puoi fare",
    r"ce la farai",
    r"non arrenderti",
    r"credi in te stess[oa]",
    # Added mechanical endings (v4.2)
    r"spero sia utile",
    r"spero di averti aiutato",
    r"ecco quello che ho trovato",
    r"fammi sapere se hai bisogno di altro",
    r"vuoi sapere altro",
    r"cos'altro posso fare",
    r"posso aiutarti con qualcosa",
    r"sono a tua disposizione",
    r"ti ascolto",
    r"ti sto ascoltando",
    r"sono qui con te",
    r"ci sono\.?",
    r"eccomi\.?",
    r"^come posso aiutarti\??$",
]

# Compiled for performance
_BLACKLIST_COMPILED = [re.compile(p, re.IGNORECASE) for p in TEMPLATE_BLACKLIST]

_BOT_SPEAKER_RE = re.compile(
    r"^\s*(?:genesi|assistant|assistente|bot|ai|nome\s*del\s*bot)\s*:\s*",
    re.IGNORECASE,
)
_NAME_SPEAKER_RE = re.compile(
    r"^\s*([A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ'’-]{1,24})\s*:\s+(.+)$",
    re.DOTALL,
)
_ASSISTANT_OPENERS_RE = re.compile(
    r"^(?:s[iì]|ok|okay|va bene|certo|certamente|procedo|perfetto|ti rispondo|"
    r"ecco|capito|ricevuto|fatto|dimmi|tranquill[oa])\b",
    re.IGNORECASE,
)


# ═══════════════════════════════════════════════════════════════
# LOOP DETECTOR — blocca risposte identiche consecutive (FASE 4)
# ═══════════════════════════════════════════════════════════════

# user_id -> last response text
_last_responses: dict = defaultdict(str)
# user_id -> consecutive identical count
_repeat_counts: dict = defaultdict(int)


def _normalize_for_comparison(text: str) -> str:
    """Normalize text for loop comparison (lowercase, strip, collapse whitespace)."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def strip_leading_speaker_prefix(response: str) -> str:
    """
    Rimuove prefissi speaker iniziali generati dal modello, senza toccare citazioni interne.

    I prefissi del bot/assistant vengono sempre rimossi. I prefissi con nome proprio
    vengono rimossi solo quando il testo dopo i due punti assomiglia a una risposta
    diretta dell'assistente, evitando casi narrativi tipo "Marco: ha detto...".
    """
    if not response or not isinstance(response, str):
        return response

    cleaned = _BOT_SPEAKER_RE.sub("", response, count=1).lstrip()
    if cleaned != response:
        return cleaned

    match = _NAME_SPEAKER_RE.match(response)
    if not match:
        return response

    rest = match.group(2).lstrip()
    if _ASSISTANT_OPENERS_RE.search(rest):
        return rest
    return response


# ═══════════════════════════════════════════════════════════════
# MAIN FILTER
# ═══════════════════════════════════════════════════════════════

def filter_response(response: str, user_id: str = "") -> str:
    """
    Filtro post-generazione. Chiamato PRIMA del return finale.
    
    1. Rimuove frasi blacklisted (template, meta-meccaniche)
    2. Blocca loop risposte identiche
    3. Pulisce risultato
    
    Returns:
        Risposta filtrata, o None se deve essere rigenerata
    """
    if not response or not response.strip():
        return response

    original = response
    filtered = strip_leading_speaker_prefix(response)

    # STEP 1: Strip blacklisted phrases
    for pattern in _BLACKLIST_COMPILED:
        filtered = pattern.sub("", filtered)

    # Clean up double spaces and leading/trailing whitespace
    filtered = re.sub(r'\s{2,}', ' ', filtered).strip()
    # Clean up orphaned punctuation at start
    filtered = re.sub(r'^[,.\s]+', '', filtered).strip()

    if filtered != original:
        logger.info("RESPONSE_FILTER_STRIPPED user=%s removed_patterns=true", user_id)

    # STEP 2: If filtering emptied the response, return minimal
    if not filtered or len(filtered) < 3:
        logger.warning("RESPONSE_FILTER_EMPTY user=%s original_len=%d", user_id, len(original))
        return ""  # Signal to caller that regeneration is needed

    # STEP 3: Loop detection (FASE 4)
    if user_id:
        normalized = _normalize_for_comparison(filtered)
        last = _last_responses[user_id]

        if normalized == last and last:
            _repeat_counts[user_id] += 1
            count = _repeat_counts[user_id]
            logger.warning("RESPONSE_LOOP_DETECTED user=%s count=%d", user_id, count)
            if count >= 1:
                # Hard block — signal regeneration needed
                return ""
        else:
            _repeat_counts[user_id] = 0

        _last_responses[user_id] = normalized

    return filtered


def contains_blacklisted(text: str) -> bool:
    """Check if text contains any blacklisted pattern. For testing."""
    text_lower = text.lower()
    for pattern in _BLACKLIST_COMPILED:
        if pattern.search(text_lower):
            return True
    return False
