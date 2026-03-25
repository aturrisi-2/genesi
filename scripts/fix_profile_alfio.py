"""
Script one-shot: pulisce il profilo di Alfio dai dati corrotti.
Da eseguire UNA SOLA VOLTA su Ubuntu:
  cd /opt/genesi && python3 scripts/fix_profile_alfio.py
"""
import json
import sys
from pathlib import Path

USER_ID = "6028d92a-94f2-4e2f-bcb7-012c861e3ab2"
PROFILE_PATH = Path(f"memory/profile/{USER_ID}.json")

if not PROFILE_PATH.exists():
    print(f"ERRORE: {PROFILE_PATH} non trovato")
    sys.exit(1)

with open(PROFILE_PATH, "r", encoding="utf-8") as f:
    profile = json.load(f)

print("=== PROFILO PRIMA ===")
print(f"  city:       {profile.get('city')}")
print(f"  profession: {profile.get('profession')}")
print(f"  interests:  {profile.get('interests')}")
print(f"  children:   {profile.get('children')}")
print(f"  pets:       {profile.get('pets')}")

changes = []

# 0. Reset campi artefatti di test (Marco Ferrara, Laura) per non influenzare il prossimo test
_TEST_NAMES = {"marco ferrara", "marco", "ferrara", "mariella"}
if (profile.get("name") or "").lower() in _TEST_NAMES:
    profile["name"] = "Alfio"
    changes.append(f"name ripristinato ad Alfio (era artefatto test: '{profile.get('name')}')")
# Reset se name == città (bug: city salvata come name)
_current_name = (profile.get("name") or "").lower().strip()
_current_city = (profile.get("city") or "").lower().strip()
if _current_name and _current_city and _current_name == _current_city:
    profile["name"] = "Alfio"
    changes.append(f"name ripristinato a Alfio (era '{_current_name}' = city)")
_TEST_SPOUSES = {"laura"}
if (profile.get("spouse") or "").lower() in _TEST_SPOUSES:
    profile["spouse"] = None
    changes.append("spouse rimosso (artefatto test Laura)")

# 1. City: se è corrotta (non è Imola), ripristina
bad_cities = {"Roma", "Razza Europea", "Professione Cuoco", None, ""}
if profile.get("city") in bad_cities:
    profile["city"] = "Imola"
    changes.append("city → Imola")

# 2. Profession: rimuovi se corrotta da artefatti di test o frasi emotive
bad_professions = {"persiani", "leclerc e hamilton", "professione cuoco", "cuoco"}
current_prof = profile.get("profession") or ""
current_prof_lower = current_prof.lower()
if current_prof_lower in bad_professions:
    profile["profession"] = None
    changes.append(f"profession rimossa ({current_prof})")
# Rimuovi frasi emotive/narrative finite in profession per bug CME
_EMOTIONAL_FRAGMENTS = ["scosso", "distrutto", "preoccupato", "agitato", "emozionato",
                        "stanco", "felice", "triste", "arrabbiato", "ancora molto"]
if any(frag in current_prof_lower for frag in _EMOTIONAL_FRAGMENTS):
    profile["profession"] = None
    changes.append(f"profession rimossa (frammento emotivo: '{current_prof}')")

# 3. Interests: rimuovi 'gatti persiani' (falso positivo)
interests = profile.get("interests", [])
original_len = len(interests)
interests = [i for i in interests if "persiani" not in i.lower()]
if len(interests) != original_len:
    profile["interests"] = interests
    changes.append("interests: rimosso 'gatti persiani'")

# 4. Children: rimuovi Marco (artefatto di test)
children = profile.get("children", [])
original_len = len(children)
children = [c for c in children if (c.get("name", "") if isinstance(c, dict) else str(c)).lower() != "marco"]
if len(children) != original_len:
    profile["children"] = children
    changes.append("children: rimosso Marco (artefatto test)")

# 5. Pets: assicura che Mignolo e Prof ci siano
pets = profile.get("pets", [])
existing_names = {(p.get("name", "") if isinstance(p, dict) else str(p)).lower() for p in pets}
if "mignolo" not in existing_names:
    pets.append({"type": "cat", "name": "Mignolo"})
    changes.append("pets: aggiunto Mignolo")
if "prof" not in existing_names:
    pets.append({"type": "cat", "name": "Prof"})
    changes.append("pets: aggiunto Prof")
if "rio" not in existing_names:
    pets.append({"type": "dog", "name": "Rio"})
    changes.append("pets: aggiunto Rio")
profile["pets"] = pets

if changes:
    from datetime import datetime
    profile["updated_at"] = datetime.utcnow().isoformat()
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print("\n=== MODIFICHE APPLICATE ===")
    for c in changes:
        print(f"  ✓ {c}")
else:
    print("\n=== NESSUNA MODIFICA NECESSARIA ===")

print("\n=== PROFILO DOPO ===")
print(f"  city:       {profile.get('city')}")
print(f"  profession: {profile.get('profession')}")
print(f"  interests:  {profile.get('interests')}")
print(f"  children:   {profile.get('children')}")
print(f"  pets:       {profile.get('pets')}")
