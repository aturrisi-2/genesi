#!/usr/bin/env python3
"""
Cleanup script per profili utente Genesi.
Rimuove dati sporchi accumulati da bug precedenti:
- traits: nomi propri, forme flesse duplicate, etichette "nome: X", oggetti non-stringa
- preferences: duplicati simili per orario cena, valori incoerenti
- spouse: tronca dopo "ed ho" e simili

Uso: sudo python3 scripts/cleanup_profile.py [user_id]
     Se user_id non specificato, pulisce tutti i profili.
"""
import json
import os
import sys
import re
from pathlib import Path

MEMORY_BASE = Path("/opt/genesi/memory/profile")
if not MEMORY_BASE.exists():
    # Fallback per ambiente dev
    MEMORY_BASE = Path("/workspaces/genesi/memory/profile")

# Aggettivi da tenere (indicativi di tratti reali)
VALID_TRAIT_PATTERN = re.compile(
    r"^(appassionat[oa]|determinat[oa]|dedic[ao]t[oa]|impegnat[oa]|"
    r"attenT[oa]|resiliente|forte|precis[oa]|curios[oa]|motivat[oa]|"
    r"organizzat[oa]|premur[oa]s[oa]|tifoso\s+dell?'?\w+|"
    r"amante\s+della\s+\w+|sportiv[oa])$",
    re.IGNORECASE
)

# Pattern da scartare sempre
TRASH_PATTERNS = [
    re.compile(r"^nome\s*:", re.IGNORECASE),          # "nome: mario rossi"
    re.compile(r"^[A-Z][a-z]+\s+[A-Z][a-z]+$"),       # "Marco Ferrara" (nome cognome)
    re.compile(r"\blavo[r]\w+\b", re.IGNORECASE),      # parole legate a lavoro
]

# Voci orario cena da consolidare
DINNER_VARIANTS = {
    "cena alle 19:30", "cenare alle 19:30", "cena alle 19",
    "cena alle 21", "cena alle 21:00", "cenare alle 21",
    "aperto a cene alle 21", "aperto a cene alle 19:30",
    "cena: 21:00", "cena: 19:30",
}


def clean_spouse(value):
    """Tronca 'Rita ed ho' → 'Rita'."""
    if not isinstance(value, str):
        return value
    m = re.match(r"^(\w+)\s+(?:ed|e|ma|però|che|ho|aveva)", value, re.IGNORECASE)
    if m:
        return m.group(1)
    return value


def clean_traits(traits):
    """Rimuove duplicati, nomi propri, etichette, oggetti non-stringa."""
    if not isinstance(traits, list):
        return []
    seen = set()
    result = []
    for t in traits:
        if not isinstance(t, str):
            continue
        t = t.strip()
        tl = t.lower()
        if not t or tl in seen:
            continue
        # Scarta pattern spazzatura
        if any(p.search(t) for p in TRASH_PATTERNS):
            print(f"  TRAITS REMOVE trash: {t!r}")
            continue
        seen.add(tl)
        result.append(t)
    return result


def clean_preferences(prefs):
    """
    Normalizza la lista preferences:
    - rimuove duplicati
    - consolida varianti cena
    - rimuove valori troppo corti o palesemente sporchi
    """
    if isinstance(prefs, dict):
        # Converti dict strutturato in lista piatta
        flat = []
        for vals in prefs.values():
            if isinstance(vals, list):
                flat.extend(vals)
        prefs = flat
    if not isinstance(prefs, list):
        return []

    seen = set()
    result = []
    best_dinner = None

    for p in prefs:
        if not isinstance(p, str):
            continue
        p = p.strip()
        pl = p.lower()

        # Gestisci varianti orario cena — tieni solo la più recente
        if pl in DINNER_VARIANTS or re.match(r"cen[ae].*\d{1,2}(:\d{2})?", pl):
            # Prendi la versione con "cena alle XX" normalizzata
            hour_m = re.search(r"(\d{1,2})(?::\d{2})?", p)
            if hour_m:
                best_dinner = f"cena alle {hour_m.group(1)}"
            continue

        if not p or len(p) < 3 or pl in seen:
            continue
        seen.add(pl)
        result.append(p)

    if best_dinner and best_dinner.lower() not in seen:
        result.append(best_dinner)

    return result


def clean_profile(data: dict) -> dict:
    changed = False

    # spouse
    old_spouse = data.get("spouse")
    new_spouse = clean_spouse(old_spouse)
    if new_spouse != old_spouse:
        print(f"  SPOUSE: {old_spouse!r} → {new_spouse!r}")
        data["spouse"] = new_spouse
        changed = True

    # traits
    old_traits = data.get("traits", [])
    new_traits = clean_traits(old_traits)
    if new_traits != old_traits:
        removed = set(str(t) for t in old_traits) - set(new_traits)
        print(f"  TRAITS: removed {len(old_traits) - len(new_traits)} → {sorted(removed)}")
        data["traits"] = new_traits
        changed = True

    # preferences
    old_prefs = data.get("preferences", [])
    new_prefs = clean_preferences(old_prefs)
    if new_prefs != old_prefs:
        print(f"  PREFS: {len(old_prefs)} → {len(new_prefs)}: {new_prefs}")
        data["preferences"] = new_prefs
        changed = True

    return data, changed


def process_file(path: Path):
    print(f"\n--- {path.name} ---")
    with open(path) as f:
        data = json.load(f)

    name = data.get("name", "?")
    print(f"  User: {name}")

    data, changed = clean_profile(data)

    if changed:
        with open(path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  ✓ Salvato")
    else:
        print(f"  (nessuna modifica)")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        uid = sys.argv[1]
        p = MEMORY_BASE / f"{uid}.json"
        if not p.exists():
            print(f"File non trovato: {p}")
            sys.exit(1)
        process_file(p)
    else:
        files = list(MEMORY_BASE.glob("*.json"))
        print(f"Trovati {len(files)} profili in {MEMORY_BASE}")
        for f in files:
            try:
                process_file(f)
            except Exception as e:
                print(f"  ERRORE {f.name}: {e}")
    print("\nDone.")
