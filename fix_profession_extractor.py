"""
FIX: Cognitive Profession Extractor — garbling bug
===================================================
BUG confermato dai log e dal test:

    COGNITIVE_PROFESSION_EXTRACT value='più necessari nel programma'
    COGNITIVE_PROFESSION_UPDATED old=... new='più necessari nel programma'
    profile profession='contento di sentirlo alfio hai avuto modo di dedicarti a'

CAUSA: il prompt LLM per l'estrazione della profession non ha vincoli
       sufficienti — estrae qualsiasi frase che "sembra" una descrizione
       professionale, incluso testo conversazionale.

FIX: cercare nel file che gestisce COGNITIVE_PROFESSION_EXTRACT
     e applicare le modifiche qui sotto.

Passi per trovare il file:
    grep -rn "COGNITIVE_PROFESSION_EXTRACT\|profession_extract\|COGNITIVE_PROFESSION_UPDATED" /opt/genesi --include="*.py"

Tipicamente è in uno di questi:
    core/brain.py
    core/cognitive_engine.py
    core/proactor.py  (sezione cognitive)
    core/identity_extractor.py
"""

# ─── PATCH 1: validazione post-estrazione ────────────────────────────────────
#
# Dopo aver ricevuto il valore dalla LLM, aggiungere questa funzione
# di validazione PRIMA di salvare la profession nel profilo.

CONVERSATIONAL_GARBAGE = [
    # testo conversazionale
    "ciao", "grazie", "prego", "sentirlo", "contento", "bene", "bello",
    "perfetto", "capito", "benissimo", "mi fa piacere", "dai",
    # frammenti di contesto tecnico (da coding_user)
    "più necessari", "nel programma", "necessari nel",
    "oggetti non più", "libera lo spazio",
    # frasi incomplete/dipendenti
    "hai avuto modo", "dedicarti a", "avuto modo di",
    # articoli/preposizioni isolati (mai una profession valida)
    " della ", " nel ", " del ",
]

PROFESSION_MIN_LENGTH = 3
PROFESSION_MAX_LENGTH = 80


def is_valid_profession(value: str) -> bool:
    """
    Restituisce True solo se 'value' sembra una professione reale.

    Criteri:
    - lunghezza ragionevole
    - non contiene frammenti conversazionali
    - non è un frammento di frase (inizia con lettera maiuscola o è un ruolo noto)
    """
    if not value or not isinstance(value, str):
        return False

    value = value.strip()

    # Lunghezza
    if len(value) < PROFESSION_MIN_LENGTH or len(value) > PROFESSION_MAX_LENGTH:
        return False

    # Contiene spazzatura conversazionale
    v_lower = value.lower()
    for garbage in CONVERSATIONAL_GARBAGE:
        if garbage.lower() in v_lower:
            return False

    # Non deve essere una frase lunga con verbi comuni (è testo, non professione)
    verb_indicators = [
        " ho ", " hai ", " ha ", " è ", " sono ", " siamo ",
        " che ", " per fare ", " per ", " a fare ",
        " della ", " dello ", " degli ", " delle ",
    ]
    for vi in verb_indicators:
        if vi in f" {v_lower} ":
            return False

    return True


# ─── PATCH 2: prompt LLM migliorato ─────────────────────────────────────────
#
# Sostituire il prompt corrente per l'estrazione della profession con:

PROFESSION_EXTRACTION_PROMPT = """
Analizza il seguente testo e identifica la professione o il ruolo professionale 
dell'utente, SE esplicitamente menzionato.

REGOLE STRICT:
- Restituisci SOLO il ruolo/titolo professionale (es: "ingegnere software", 
  "construction manager", "medico", "insegnante")
- Se la professione NON è chiaramente menzionata, restituisci null
- NON restituire frasi conversazionali, ringraziamenti, o contesto tecnico
- NON restituire frammenti di codice o descrizioni di algoritmi
- La risposta deve essere un sostantivo/ruolo, non una frase

Testo: {text}

Profession (solo il ruolo, o null):
"""


# ─── PATCH 3: codice di integrazione ─────────────────────────────────────────
#
# Nel file che chiama COGNITIVE_PROFESSION_EXTRACT, modificare così:

def extract_profession_safe(raw_value: str, existing_profession: str = None) -> str | None:
    """
    Wrapper sicuro per l'estrazione della profession.
    
    Ritorna:
    - Il nuovo valore se valido
    - existing_profession se il nuovo valore non è valido (non sovrascrivere)
    - None se non c'è nulla di valido
    """
    if not raw_value:
        return existing_profession

    cleaned = raw_value.strip().strip('"\'').strip()

    if not is_valid_profession(cleaned):
        # Log: COGNITIVE_PROFESSION_SKIP reason=invalid_value value=...
        print(f"[COGNITIVE_PROFESSION_SKIP] value='{cleaned}' - testo non valido come professione")
        return existing_profession  # mantieni quello vecchio invece di sovrascrivere con spazzatura

    return cleaned


# ─── APPLICAZIONE ────────────────────────────────────────────────────────────
#
# Cerca nel tuo codice questo pattern (nome variabile può variare):
#
#   PRIMA (buggy):
#   ┌─────────────────────────────────────────────────────────┐
#   │  new_profession = llm_response.get("profession")        │
#   │  if new_profession:                                      │
#   │      profile["profession"] = new_profession             │
#   │      logger.info("COGNITIVE_PROFESSION_UPDATED ...")    │
#   └─────────────────────────────────────────────────────────┘
#
#   DOPO (fix):
#   ┌─────────────────────────────────────────────────────────┐
#   │  raw_profession = llm_response.get("profession")        │
#   │  validated = extract_profession_safe(                   │
#   │      raw_profession,                                    │
#   │      existing_profession=profile.get("profession")      │
#   │  )                                                       │
#   │  if validated and validated != profile.get("profession"):│
#   │      profile["profession"] = validated                  │
#   │      logger.info("COGNITIVE_PROFESSION_UPDATED ...")    │
#   │  else:                                                   │
#   │      logger.debug("COGNITIVE_PROFESSION_SKIP ...")      │
#   └─────────────────────────────────────────────────────────┘


# ─── SCRIPT DI RICERCA AUTOMATICA ────────────────────────────────────────────
#
# Incolla questo nel terminal del VPS per trovare esattamente dove intervenire:

SEARCH_SCRIPT = """
#!/bin/bash
echo "=== File con COGNITIVE_PROFESSION ==="
grep -rn "COGNITIVE_PROFESSION\\|profession_extract\\|profession.*=.*llm\\|profession.*update" \\
    /opt/genesi --include="*.py" | grep -v "test_genesi\\|__pycache__"

echo ""
echo "=== Contesto (5 righe attorno) ==="
grep -rn "COGNITIVE_PROFESSION_UPDATED" /opt/genesi --include="*.py" -A 3 -B 3 | \\
    grep -v "__pycache__"
"""

if __name__ == "__main__":
    # Test rapido della validazione
    test_cases = [
        ("construction manager", True),
        ("ingegnere software", True),
        ("medico", True),
        ("contento di sentirlo alfio hai avuto modo di dedicarti a", False),
        ("più necessari nel programma", False),
        ("ai", False),   # troppo corto
        ("", False),
        ("oggetti non più necessari nel programma liberando la memoria", False),
        ("sviluppatore Python", True),
        ("architetto", True),
    ]

    print("Test validazione profession:\n")
    all_pass = True
    for value, expected in test_cases:
        result = is_valid_profession(value)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"  {status} '{value[:50]}...' → {result} (atteso: {expected})"
              if len(value) > 50 else
              f"  {status} '{value}' → {result} (atteso: {expected})")

    print(f"\n{'Tutti i test passano ✅' if all_pass else 'Alcuni test falliscono ❌'}")
    print("\nCerca il file da modificare con:")
    print("  grep -rn 'COGNITIVE_PROFESSION_UPDATED' /opt/genesi --include='*.py' -B5 -A3")
