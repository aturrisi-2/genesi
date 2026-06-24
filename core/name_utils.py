"""
name_utils.py — Validazione e sanitizzazione centralizzata dei nomi propri.

Usato da tutti i servizi che estraggono nomi da testo:
cognitive_memory_engine, proactor, personal_facts_service, face_memory_service.

Principio: un sistema maturo non salva mai "mia mamma" come nome. Salva "Iolanda".
"""

import re
from typing import Optional

_COMMON_FIRST_NAMES = {
    "alessandro", "alessandra", "ale", "alfio", "andrea", "anna", "antonio",
    "carlo", "claudio", "daniele", "davide", "domenico", "elena", "fabio",
    "francesca", "francesco", "fra", "giovanni", "giulia", "giuseppe",
    "luca", "luigi", "marco", "maria", "mario", "michele", "mimmo", "paolo",
    "pino", "rita", "roberto", "sara", "sofia", "stefano",
}

# Nomi propri composti comuni: due token separati che formano UN solo nome.
# Conservativo: si attiva solo se i due token compaiono separati e adiacenti.
# "Gianluca" già scritto unito resta unito (non viene mai spezzato qui).
_COMPOSITE_FIRST_NAMES = {
    ("maria", "grazia"),
    ("gian", "luca"),
    ("giovan", "battista"),
    ("pier", "paolo"),
    ("anna", "maria"),
}

# Particelle / preposizioni di cognome ("Di Dio", "De Luca", "Van Gogh").
# Non sono mai nomi propri: non vanno mai restituite come first_name.
_NAME_PARTICLES = {
    "di", "de", "del", "della", "delle", "dei", "degli",
    "da", "dal", "dalla", "van", "von",
}

_DISPLAY_NAME_STOPWORDS = {
    "admin", "arch", "assistente", "bot", "capo", "dott", "dottore", "dottssa",
    "geom", "ing", "officina", "reparto", "service", "servizio", "sig",
    "sigra", "squadra", "ufficio", "zio", "zia",
}

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


def _clean_display_name(display_name: str) -> str:
    text = str(display_name or "")
    text = re.sub(r"[_/|]+", " ", text)
    text = re.sub(r"[^\w\sÀ-ÖØ-öø-ÿ'’.+-]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:80]


def extract_first_name_from_display_name(display_name: str, fallback_id: str | None = None) -> dict:
    """
    Estrae in modo prudente un probabile nome di battesimo da display name sporchi.

    Non inventa nomi: se trova solo numeri, sigle, titoli o ruoli restituisce
    first_name=None. Il display name originale resta sempre disponibile.
    """
    normalized = _clean_display_name(display_name)
    result = {
        "first_name": None,
        "confidence": 0.0,
        "source": "none",
        "reason": "empty" if not normalized else "no_confident_first_name",
        "original_display_name": display_name or "",
        "normalized_display_name": normalized,
    }
    if not normalized:
        return result

    compact_digits = re.sub(r"\D", "", normalized)
    if compact_digits and len(compact_digits) >= max(6, len(normalized.replace(" ", "")) - 3):
        result["reason"] = "phone_or_numeric"
        return result

    raw_tokens = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ'’.+-]+", normalized)
    candidates = []
    for index, raw in enumerate(raw_tokens):
        token = raw.strip(" .'’-+")
        if not token:
            continue
        low = token.lower()
        if len(token) == 1 or re.fullmatch(r"[A-Z]\.?", token):
            continue
        if low in _DISPLAY_NAME_STOPWORDS:
            continue
        if token.isupper() and low not in _COMMON_FIRST_NAMES:
            continue
        candidates.append((index, token.title(), low))

    if not candidates:
        result["reason"] = "only_roles_titles_numbers_or_acronyms"
        return result

    # Nome composto: due candidati separati e adiacenti che formano un nome unico
    # (es. "Maria Grazia", "Giovan Battista"). Ha priorità sul primo nome singolo.
    for i in range(len(candidates) - 1):
        idx_a, token_a, low_a = candidates[i]
        idx_b, token_b, low_b = candidates[i + 1]
        if idx_b == idx_a + 1 and (low_a, low_b) in _COMPOSITE_FIRST_NAMES:
            result.update({
                "first_name": f"{token_a} {token_b}",
                "confidence": 0.92 if idx_a == 0 else 0.8,
                "source": "composite_first_name",
                "reason": "known_composite_first_name",
            })
            return result

    known = [(idx, token, low) for idx, token, low in candidates if low in _COMMON_FIRST_NAMES]
    if known:
        idx, token, _ = known[0]
        confidence = 0.95 if idx == 0 else 0.82
        result.update({
            "first_name": token,
            "confidence": confidence,
            "source": "common_first_name",
            "reason": "known_first_name",
        })
        return result

    if len(candidates) == 1 and candidates[0][2] not in _NAME_PARTICLES:
        _, token, _ = candidates[0]
        result.update({
            "first_name": token,
            "confidence": 0.35,
            "source": "single_clean_token",
            "reason": "low_confidence_single_token",
        })
        return result

    # "Nome di/de/van Cognome": se il secondo token è una particella di cognome
    # (es. "... Di Dio", "... De Luca", "... Van Gogh"), il nome proprio è il
    # PRIMO token, non la particella.
    if (len(candidates) >= 2
            and candidates[0][2] not in _NAME_PARTICLES
            and candidates[1][2] in _NAME_PARTICLES):
        _, token, _ = candidates[0]
        result.update({
            "first_name": token,
            "confidence": 0.6,
            "source": "name_before_particle",
            "reason": "first_token_before_surname_particle",
        })
        return result

    # Forma "Cognome Nome [Cognome...]": 3+ token, primo non è un nome noto.
    # Il nome proprio è tipicamente il primo token NON-particella dal secondo in poi
    # (es. "Rossi Pina Bianchi" → "Pina", "Turrisi Pina Nino Calvagna" → "Pina").
    # Le particelle vengono saltate. Con 2 token si assume "Nome Cognome" → primo (sotto).
    # I nomi composti noti sono già stati intercettati sopra in qualsiasi posizione.
    if len(candidates) >= 3:
        for idx, token, low in candidates[1:]:
            if low not in _NAME_PARTICLES:
                result.update({
                    "first_name": token,
                    "confidence": 0.5,
                    "source": "surname_first_guess",
                    "reason": "surname_first_second_token",
                })
                return result

    # Fallback ordine: primo candidato NON-particella.
    for idx, token, low in candidates:
        if low not in _NAME_PARTICLES:
            result.update({
                "first_name": token,
                "confidence": 0.45 if idx == 0 else 0.4,
                "source": "clean_token_order",
                "reason": "low_confidence_order_guess",
            })
            return result

    # Solo particelle: nessun nome proprio affidabile.
    result["reason"] = "only_surname_particles"
    return result


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


# ── Nomi invalidi per animali domestici ──────────────────────────────────────

# Specie — non sono nomi propri
_PET_SPECIES = {"cane", "gatto", "gatta", "uccello", "coniglio", "criceto", "criceto", "pesce",
                "tartaruga", "pappagallo", "canarino", "furretto", "hamster"}

# Razze comuni — non sono nomi propri
_PET_BREEDS = {
    "labrador", "golden", "retriever", "pastore", "husky", "bulldog", "beagle",
    "poodle", "barboncino", "chihuahua", "dachshund", "boxer", "rottweiler",
    "maltese", "shih", "tzu", "border", "collie", "dobermann", "setter",
    "persiano", "siamese", "bengala", "ragdoll", "maine", "coon", "british",
    "shorthair", "scottish", "fold", "sphynx", "burmese", "abissino",
    "european", "europeo", "comune", "randagio", "meticcio", "bastardino",
}

# Colori e descrittori fisici usati al posto del nome
_PET_DESCRIPTORS = {
    "tigrato", "bianco", "nero", "marrone", "rosso", "arancione", "grigio",
    "beige", "macchiato", "soriano", "tricolore", "bicolore", "peloso",
    "piccolo", "grande", "medio", "cucciolo", "giovane", "vecchio",
    "maschio", "femmina",
}

_PET_POSSESSIVES = {
    "il mio cane", "la mia gatta", "il mio gatto", "il mio coniglio",
    "il mio uccello", "la mia tartaruga", "il mio criceto",
}

# Pronomi/articoli usati senza nome
_PET_INVALID_NAMES = _PET_SPECIES | _PET_BREEDS | _PET_DESCRIPTORS | {
    "animale", "cucciolo", "bestia", "bestiola", "peloso", "pelosa",
}


def sanitize_pet_name(name: str) -> Optional[str]:
    """
    Sanitizza un nome per il salvataggio come nome di animale domestico.

    - Rifiuta specie ("gatto"), razze ("persiano"), colori ("tigrato")
    - Rifiuta possessivi con specie ("il mio gatto", "la mia cagnolina")
    - Rifiuta nomi generico-invalidi (stessa logica di sanitize_profile_name)
    - Capitalizza correttamente

    Ritorna il nome pulito o None se da rifiutare.
    """
    if not name or not isinstance(name, str):
        return None

    name = name.strip()
    nl = name.lower()

    # Blocca possessivi con specie ("il mio gatto", "la mia gatta")
    if any(nl == p or nl.startswith(p) for p in _PET_POSSESSIVES):
        return None

    # Blocca specie/razze/colori
    if nl in _PET_INVALID_NAMES:
        return None

    # Blocca se è un aggettivo descrittivo + specie ("gatto tigrato", "cane marrone")
    parts = nl.split()
    if len(parts) == 2 and (parts[0] in _PET_SPECIES or parts[1] in _PET_SPECIES):
        return None
    if len(parts) == 2 and (parts[0] in _PET_BREEDS or parts[1] in _PET_BREEDS):
        return None

    # Usa la stessa logica di sanitize_profile_name per nomi generici invalidi
    return sanitize_profile_name(name)
