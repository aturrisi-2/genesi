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
# PROMPT-LEAK FILTER — blocca sezioni di prompt interno copiate
# letteralmente nella risposta (FASE anti-leak gruppi)
# ═══════════════════════════════════════════════════════════════

# Keyword che identificano una sezione INTERNA del prompt. Se compaiono dentro
# un blocco [...] o come titolo di riga, quel pezzo non deve mai uscire all'utente.
# Nessun hardcoding di nomi: solo etichette strutturali del prompt.
_LEAK_KEYWORDS = [
    "CONTESTO FAMIGLIA",
    "CONTESTO",
    "REGOLE DI INFERENZA",
    "REGOLA FONDAMENTALE",
    "REGOLE ASSOLUTE",
    "REGOLE",
    "DISCUSSIONE IN CORSO",
    "FINE DISCUSSIONE",
    "RISPOSTE RECENTI",
    "FINE RISPOSTE",
    "COSA SO DI",
    "DINAMICHE DELLA FAMIGLIA",
    "RIEPILOGO DISCUSSIONI",
    "ATTENZIONE ASSOLUTA",
    "SOLLECITAZIONE",
    "GRUPPO FAMILIARE",
    "GRUPPO:",
    "GRUPPO ",
    "SISTEMA:",
    "PROMPT:",
    "ISTRUZIONI:",
    "DEVI RISPONDERE",
    "RISPONDI SOLO",
    "NON NOMINARE",
    "NON SEI NEL GRUPPO",
    "TRATTALO",
    "TRATTALA",
    "LINEE GUIDA",
]
_LEAK_KW_RE = re.compile("|".join(re.escape(k) for k in _LEAK_KEYWORDS), re.IGNORECASE)

# Blocco [...] (non annidato) che contiene almeno una keyword interna.
_LEAK_BRACKET_RE = re.compile(r"\[[^\[\]]*\]", re.DOTALL)

# Riga-trascrizione del contesto gruppo: "[10s fa] Marco: ..." o "→ Genesi: ..."
_LEAK_TRANSCRIPT_RE = re.compile(
    r"^\s*(?:\[\s*\d+\s*(?:s|min|h|sec|ore|minuti)\b[^\]]*\]\s*)?[^\n:]{1,30}:\s",
    re.IGNORECASE,
)
_LEAK_GENESI_LINE_RE = re.compile(r"^\s*(?:→\s*)?genesi\s*:", re.IGNORECASE)

# Istruzioni imperative interne ("Rispondi SOLO a...", "NON nominare...") fuori da []
_LEAK_IMPERATIVE_RE = re.compile(
    r"^\s*(?:rispondi solo\b|devi rispondere\b|non nominare\b|trattal[oa]\b|non sei nel gruppo\b|"
    r"regola fondamentale\b|regole assolute\b|linee guida\b)",
    re.IGNORECASE,
)
_LEAK_PREFIX_TO_BOT_RE = re.compile(
    r"^\s*(?:(?:con\s+coerenza\s+)?se\s+rilevante:\]|oggi\s+[èe]\b|"
    r"sistema\s*:|prompt\s*:|istruzioni\s*:|devi\s+rispondere\b)"
    r".*?\bgenesi\s*:\s*",
    re.IGNORECASE | re.DOTALL,
)
_LEAK_LEADING_FRAGMENT_RE = re.compile(
    r"^\s*(?:(?:con\s+coerenza\s+)?se\s+rilevante:\]|"
    r"sistema\s*:|prompt\s*:|istruzioni\s*:|devi\s+rispondere\b)\s*",
    re.IGNORECASE,
)


def _bracket_has_leak(block: str) -> bool:
    """True se un blocco [...] contiene una keyword di prompt interno."""
    return bool(_LEAK_KW_RE.search(block))


def strip_internal_prompt_leak(text: str) -> tuple[str, bool]:
    """
    Rimuove dalla risposta i frammenti di prompt interno copiati dal modello.

    Ritorna (testo_pulito, heavy_leak):
      - testo_pulito: risposta senza sezioni interne;
      - heavy_leak: True se la contaminazione è grave (caller deve usare
        fallback/rigenerazione invece di mandare il residuo).

    Conserva le parentesi quadre "innocue" (es. emote [ride], [sorride]):
    rimuove solo blocchi che contengono keyword strutturali del prompt.
    """
    if not text or not isinstance(text, str):
        return text, False

    original = text
    orig_len = len(original.strip())

    # 1) Rimuovi blocchi [...] che contengono keyword interne (preserva emote)
    cleaned = _LEAK_BRACKET_RE.sub(
        lambda m: "" if _bracket_has_leak(m.group(0)) else m.group(0),
        text,
    )

    # 1b) Se un prefisso interno tronco precede "Genesi:", taglia tutto il
    # contesto leak e conserva solo la risposta effettiva del bot.
    prefix_to_bot_cut = bool(_LEAK_PREFIX_TO_BOT_RE.search(cleaned))
    cleaned = _LEAK_PREFIX_TO_BOT_RE.sub("", cleaned, count=1)
    cleaned = _LEAK_LEADING_FRAGMENT_RE.sub("", cleaned, count=1)

    # 2) Pulizia riga per riga: titoli interni, trascrizioni gruppo, imperativi
    kept_lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append(line)
            continue
        if _LEAK_GENESI_LINE_RE.match(stripped):
            continue
        if _LEAK_IMPERATIVE_RE.match(stripped):
            continue
        # riga interamente MAIUSCOLA che è un titolo di sezione interna
        if _LEAK_KW_RE.search(stripped) and stripped == stripped.upper() and len(stripped) > 3:
            continue
        # trascrizione "[Xs fa] Nome:" tipica del contesto gruppo iniettato
        if stripped.startswith("[") and _LEAK_TRANSCRIPT_RE.match(stripped):
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines)

    # 3) Normalizza spazi/righe vuote multiple
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"^[,.\s]+", "", cleaned).strip()
    cleaned = strip_leading_speaker_prefix(cleaned)

    if cleaned == original.strip():
        return original, False

    clean_len = len(cleaned)
    # Heavy leak: residuo troppo eroso, vuoto, o keyword critica ancora presente
    heavy = (
        clean_len < 3
        or (orig_len > 0 and clean_len < orig_len * 0.5 and not prefix_to_bot_cut)
        or bool(_LEAK_KW_RE.search(cleaned))
    )
    logger.info(
        "RESPONSE_LEAK_STRIPPED removed_chars=%d heavy=%s",
        orig_len - clean_len, heavy,
    )
    return cleaned, heavy


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

    # STEP 0: Anti prompt-leak — rimuovi sezioni di prompt interno copiate.
    # Se la contaminazione è grave, segnala rigenerazione (return "").
    filtered, heavy_leak = strip_internal_prompt_leak(filtered)
    if heavy_leak:
        logger.warning("RESPONSE_LEAK_HEAVY user=%s — signaling regeneration", user_id)
        return ""

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
