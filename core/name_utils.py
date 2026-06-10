"""
name_utils.py — Validazione e sanitizzazione centralizzata dei nomi propri.

Usato da tutti i servizi che estraggono nomi da testo:
cognitive_memory_engine, proactor, personal_facts_service, face_memory_service.

Principio: un sistema maturo non salva mai "mia mamma" come nome. Salva "Iolanda".
"""

import re
from typing import Optional

# ── Sostantivi relazionali che NON sono nomi propri ──────────────────────────

_RELATIONAL_NOUNS = {
    "mamma", "mama", "papà", "papa", "padre", "madre",
    "figlio", "figlia", "fratello", "sorella",
    "marito", "moglie", "nonno", "nonna",
    "zio", "zia", "cugino", "cugina", "nipote",
    "partner", "compagna", "compagno",
    "fidanzata", "fidanzato", "genero", "nuora",
    "suocero", "suocera", "cognato", "cognata",
}

_POSSESSIVES = {"mia", "mio", "sua", "suo", "tua", "tuo", "nostra", "nostro", "loro"}

# Prefisso: (possessivo|articolo)_spazio_(sostantivo_relazionale)
_RELATIONAL_PREFIX_RE = re.compile(
    r"^(mia|mio|sua|suo|tua|tuo|nostra|nostro|la|il|lo|le)[\s_]+"
    r"(mamma|mama|pap[aà]|padre|madre|figlio|figlia|fratello|sorella|"
    r"marito|moglie|nonno|nonna|zio|zia|cugino|cugina|nipote|"
    r"partner|compagna|compagno|fidanzata|fidanzato|genero|nuora|"
    r"suocero|suocera|cognato|cognata)",
    re.IGNORECASE,
)

# Placeholder generici da rifiutare
_INVALID_NAMES = {
    "unknown", "sconosciuto", "ignoto", "persona",
    "nessuno", "qualcuno", "qualcosa",
    "io", "lui", "lei", "tu", "noi", "voi", "loro",
    "ragazzo", "ragazza", "uomo", "donna", "bambino", "bambina",
}


def is_relational_descriptor(name: str) -> bool:
    """
    True se il testo è un descrittore relazionale (non un nome proprio).

    Esempi:
    - "mia mamma" → True
    - "suo marito Gianvito" → True (inizia con relazionale)
    - "Iolanda" → False
    - "mio_figlio" → True (con underscore, come da face_memory_service)
    """
    if not name:
        return False
    n = name.strip()
    nl = n.lower()

    # Sostantivo relazionale nudo
    if nl in _RELATIONAL_NOUNS:
        return True

    # Con underscore (usato in face_memory_service per file names)
    n_us = nl.replace(" ", "_")
    if _RELATIONAL_PREFIX_RE.match(n_us) or _RELATIONAL_PREFIX_RE.match(nl):
        return True

    return False


def extract_proper_name(text: str) -> Optional[str]:
    """
    Dato un testo che può contenere prefisso relazionale + nome proprio,
    ritorna SOLO il nome proprio, oppure None se è puramente relazionale.

    Esempi:
    - "mia mamma Iolanda"    → "Iolanda"
    - "mio figlio Ennio"     → "Ennio"
    - "mia sorella Mariella" → "Mariella"
    - "mia mamma"            → None
    - "Iolanda"              → "Iolanda"
    - "Rita"                 → "Rita"
    """
    if not text:
        return None

    text = text.strip()

    # Pattern: (possessivo?) (relazionale) (NomeProprio)
    m = re.match(
        r"^(?:(?:mia|mio|sua|suo|tua|tuo|nostra|nostro|la|il|lo)\s+)?"
        r"(?:mamma|mama|pap[aà]|padre|madre|figlio|figlia|fratello|sorella|"
        r"marito|moglie|nonno|nonna|zio|zia|cugino|cugina|nipote|"
        r"partner|compagna|compagno|fidanzata|fidanzato|genero|nuora|"
        r"suocero|suocera|cognato|cognata)"
        r"\s+([A-ZÀ-ÿa-zÀ-ÿ][a-zÀ-ÿ]+(?:\s+[A-ZÀ-ÿ][a-zÀ-ÿ]+)*)",
        text, re.IGNORECASE
    )
    if m:
        return m.group(1).strip().title()

    # Puramente relazionale senza nome proprio → rifiuta
    if is_relational_descriptor(text):
        return None

    return text


def sanitize_profile_name(name: str) -> Optional[str]:
    """
    Sanitizza un nome per il salvataggio in campi profilo (children, spouse, pets).

    - Strips prefissi relazionali → estrae il nome proprio
    - Rifiuta placeholder e descrittori relazionali puri
    - Limita a max 3 parole (oltre è probabilmente una frase)
    - Capitalizza correttamente

    Ritorna il nome pulito o None se il valore va rifiutato.
    """
    if not name or not isinstance(name, str):
        return None

    name = name.strip()
    if not name:
        return None

    # Tenta estrazione nome proprio da frase relazionale
    extracted = extract_proper_name(name)
    if extracted is None:
        return None

    # Rifiuta placeholder
    if extracted.lower() in _INVALID_NAMES:
        return None

    # Rifiuta se troppo lungo (frase, non nome)
    if len(extracted.split()) > 3:
        return None

    return extracted.strip().title()


def build_relational_map(profile: dict) -> str:
    """
    Costruisce una stringa di contesto per il system prompt LLM che mappa
    termini relazionali → nomi propri reali dal profilo.

    Esempio output:
    "MAPPA RELAZIONALE (usa questi nomi nelle risposte):
    - mia moglie / il mio partner → Rita
    - mia figlia → Zoe
    - mio figlio → Ennio
    - i miei figli → Zoe, Ennio"

    Se il profilo non ha dati familiari ritorna stringa vuota.
    """
    lines = []

    spouse = profile.get("spouse")
    if spouse and isinstance(spouse, str) and spouse.strip():
        lines.append(f"- 'mia moglie' / 'il mio partner' → {spouse.strip()}")

    children = profile.get("children", [])
    daughters = [c.get("name", "") for c in children
                 if isinstance(c, dict) and c.get("gender") == "F"]
    sons = [c.get("name", "") for c in children
            if isinstance(c, dict) and c.get("gender") == "M"]
    unknown_gender = [c.get("name", "") for c in children
                      if isinstance(c, dict) and c.get("gender", "?") == "?"]

    if daughters:
        lines.append(f"- 'mia figlia' → {', '.join(daughters)}")
    if sons:
        lines.append(f"- 'mio figlio' → {', '.join(sons)}")
    if len(children) > 1:
        all_names = [c.get("name", "") for c in children if isinstance(c, dict) and c.get("name")]
        if all_names:
            lines.append(f"- 'i miei figli' → {', '.join(all_names)}")

    if not lines:
        return ""

    return "MAPPA RELAZIONALE (quando l'utente usa questi termini, usa il nome proprio nella risposta):\n" + "\n".join(lines)
