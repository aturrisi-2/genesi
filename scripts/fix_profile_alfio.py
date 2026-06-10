"""
Script: pulisce il profilo di Alfio e tutti i profili dei membri del gruppo Telegram dai dati corrotti.
Da eseguire su Ubuntu:
  cd /opt/genesi && python3 scripts/fix_profile_alfio.py
"""
import json
import sys
from pathlib import Path
from datetime import datetime

USER_ID = "6028d92a-94f2-4e2f-bcb7-012c861e3ab2"
PROFILE_PATH = Path(f"memory/profile/{USER_ID}.json")
PF_PATH = Path(f"memory/personal_facts/{USER_ID}.json")
FAMILY_CACHE_PATH = Path(f"memory/telegram/family_members:{USER_ID}.json")

print("=== INIZIO PULIZIA INTEGRALE PROFILO E GRUPPO TELEGRAM ===")

# 1. Pulisci il profilo principale di Alfio
if PROFILE_PATH.exists():
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        profile = json.load(f)
    
    print("\n[1] Pulisco profilo principale Alfio...")
    profile["name"] = "Alfio"
    profile["city"] = "Imola"
    profile["timezone"] = "Europe/Rome"
    profile["profession"] = "Sviluppatore"
    profile["spouse"] = "Rita"
    
    # Pulisci figli
    bad_children = {"figlio", "mio figlio", "mia figlia", "madre", "alfio",
                    "mamma", "papà", "papa", "padre", "fratello", "sorella",
                    "marito", "moglie", "nonno", "nonna", "zio", "zia"}
    children = profile.get("children", [])
    cleaned_children = []
    for c in children:
        cname = (c.get("name") if isinstance(c, dict) else str(c)).strip()
        # Blocca nomi di test (Ztfr_*, Ztest_*) e descrittori relazionali
        if cname.lower() in bad_children:
            continue
        if cname.startswith("Ztfr_") or cname.startswith("Ztest_") or cname.startswith("ztfr_") or cname.startswith("ztest_"):
            continue
        cleaned_children.append({"name": cname})
    
    # Assicurati che Zoe ed Ennio ci siano
    child_names = {c["name"].lower() for c in cleaned_children}
    if "zoe" not in child_names:
        cleaned_children.append({"name": "Zoe"})
    if "ennio" not in child_names:
        cleaned_children.append({"name": "Ennio"})
    profile["children"] = cleaned_children

    # Pets
    pets = profile.get("pets", [])
    pet_names = {(p.get("name") if isinstance(p, dict) else str(p)).lower() for p in pets}
    cleaned_pets = []
    for p in pets:
        pname = (p.get("name") if isinstance(p, dict) else str(p)).strip()
        ptype = p.get("type") if isinstance(p, dict) else "cat"
        cleaned_pets.append({"name": pname, "type": ptype})
    
    pet_names_cleaned = {p["name"].lower() for p in cleaned_pets}
    if "mignolo" not in pet_names_cleaned:
        cleaned_pets.append({"type": "cat", "name": "Mignolo"})
    if "prof" not in pet_names_cleaned:
        cleaned_pets.append({"type": "cat", "name": "Prof"})
    if "rio" not in pet_names_cleaned:
        cleaned_pets.append({"type": "dog", "name": "Rio"})
    profile["pets"] = cleaned_pets

    # Rimuovi interessi corrotti
    interests = profile.get("interests", [])
    cleaned_interests = [i for i in interests if "persiani" not in i.lower() and "sogni" not in i.lower()]
    profile["interests"] = cleaned_interests

    profile["updated_at"] = datetime.utcnow().isoformat()
    
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    print("  ✓ Profilo principale di Alfio aggiornato con successo.")
else:
    print("  ⚠️ Profilo principale Alfio non trovato.")

# 2. Pulisci personal_facts di Alfio
if PF_PATH.exists():
    with open(PF_PATH, "r", encoding="utf-8") as f:
        pf_data = json.load(f)
    
    print("\n[2] Pulisco fatti personali di Alfio...")
    facts = pf_data.get("facts", [])
    cleaned_facts = []
    
    bad_keys = {
        "famiglia_madre_telegram_494065944",
        "famiglia_figlio_telegram_494065944",
        "famiglia_fratello_telegram_1329017213",
        "famiglia_figlia_telegram_873633028",
        "famiglia_figlia_telegram_32393144",
        "famiglia_cugina_telegram_32393144",
        "famiglia_madre_telegram_32393144"
    }
    
    for fact in facts:
        key = fact.get("key", "")
        value = fact.get("value", "").lower()
        
        # Filtra fatti autogenerati corrotti
        if key in bad_keys:
            print(f"  ✗ Rimosso fatto corrotto: {key} -> {fact.get('value')}")
            continue
        if "alfio (madre)" in value or "alfio (figlio)" in value or "mamma (madre)" in value:
            print(f"  ✗ Rimosso fatto corrotto per contenuto: {fact.get('value')}")
            continue
            
        cleaned_facts.append(fact)
        
    pf_data["facts"] = cleaned_facts
    pf_data["updated_at"] = datetime.utcnow().isoformat()
    
    with open(PF_PATH, "w", encoding="utf-8") as f:
        json.dump(pf_data, f, ensure_ascii=False, indent=2)
    print("  ✓ Fatti personali aggiornati.")
else:
    print("  ⚠️ File personal_facts non trovato.")

# 3. Pulisci e correggi i profili dei membri del gruppo Telegram
print("\n[3] Correggo i profili dei membri del gruppo Telegram...")
telegram_dir = Path("memory/telegram")

# Definisci le correzioni per ciascun ID Telegram conosciuto
member_corrections = {
    # Alfio
    "494065944": {
        "relationship_to_owner": "",
        "display_name": "Alfio",
        "gender": "M",
        "city": "Imola",
        "facts": {
            "city": "Imola"
        }
    },
    # Sandra
    "1329017213": {
        "relationship_to_owner": "sorella",
        "display_name": "Sandra",
        "gender": "F",
        "city": "Siracusa",
        "facts": {
            "relazione_con_alfio": "sorella",
            "note": "sorella di Alfio",
            "genere": "F",
            "city": "Siracusa"
        }
    },
    # Katia
    "670663120": {
        "relationship_to_owner": "sorella",
        "display_name": "Katia",
        "gender": "F",
        "city": "Siracusa",
        "facts": {
            "relazione_con_alfio": "sorella",
            "note": "sorella di Alfio",
            "genere": "F"
        }
    },
    # Mariella
    "32393144": {
        "relationship_to_owner": "sorella",
        "display_name": "Mariella",
        "gender": "F",
        "city": "Lentini",
        "facts": {
            "relazione_con_alfio": "sorella",
            "note": "sorella di Alfio",
            "genere": "F",
            "city": "Lentini"
        }
    },
    # Iolanda
    "873633028": {
        "relationship_to_owner": "madre",
        "display_name": "Iolanda",
        "gender": "F",
        "facts": {
            "relazione_con_alfio": "madre",
            "note": "madre di Alfio",
            "genere": "F"
        }
    },
    # Rita
    "552835672": {
        "relationship_to_owner": "moglie",
        "display_name": "Rita",
        "gender": "F",
        "facts": {
            "relazione_con_alfio": "moglie",
            "genere": "F"
        }
    },
    # Zoe
    "638368716": {
        "relationship_to_owner": "figlia",
        "display_name": "Zoe",
        "gender": "F",
        "facts": {
            "relazione_con_alfio": "figlia",
            "genere": "F"
        }
    },
    # Leonardo
    "1852211854": {
        "relationship_to_owner": "nipote",
        "display_name": "Leonardo",
        "gender": "M",
        "facts": {
            "relazione_con_alfio": "nipote",
            "genere": "M"
        }
    }
}

if telegram_dir.exists():
    for tid, corr in member_corrections.items():
        m_file = telegram_dir / f"group_member:{tid}.json"
        if m_file.exists():
            with open(m_file, "r", encoding="utf-8") as f:
                member = json.load(f)
            
            print(f"  Pulisco e correggo {m_file.name} ({member.get('first_name')})...")
            member["relationship_to_owner"] = corr["relationship_to_owner"]
            member["display_name"] = corr["display_name"]
            member["gender"] = corr["gender"]
            if "city" in corr:
                member["city"] = corr["city"]
            
            # Unisci i fatti
            facts = member.get("facts", {})
            facts.clear() # Cancella tutti i vecchi fatti sporchi
            facts.update(corr["facts"])
            member["facts"] = facts
            
            with open(m_file, "w", encoding="utf-8") as f:
                json.dump(member, f, ensure_ascii=False, indent=2)
            print(f"    ✓ Corretto.")
        else:
            # Se non esiste, lo creiamo pulito
            print(f"  Creazione da zero profilo pulito per {tid} ({corr['display_name']})...")
            new_member = {
                "from_id": int(tid),
                "first_name": corr["display_name"],
                "last_seen": int(datetime.utcnow().timestamp()),
                "message_count": 1,
                "joined_at": int(datetime.utcnow().timestamp()),
                "relationship_to_owner": corr["relationship_to_owner"],
                "display_name": corr["display_name"],
                "gender": corr["gender"],
                "facts": corr["facts"]
            }
            if "city" in corr:
                new_member["city"] = corr["city"]
            with open(m_file, "w", encoding="utf-8") as f:
                json.dump(new_member, f, ensure_ascii=False, indent=2)
            print(f"    ✓ Creato.")
else:
    print("  ⚠️ Directory memory/telegram non trovata.")

# 4. Pulisci la cache dei membri della famiglia
print("\n[4] Rigenero cache familiare...")
family_cache = {
  "members": [
    "Rita (relazione: moglie; genere: F)",
    "Iolanda (relazione: madre; genere: F)",
    "Mariella (relazione: sorella; città: Lentini; genere: F)",
    "Sandra (relazione: sorella; città: Siracusa; genere: F)",
    "Katia (relazione: sorella; città: Siracusa; genere: F)",
    "Zoe (relazione: figlia; genere: F)",
    "Ennio (relazione: figlio; genere: M)",
    "Leonardo (relazione: nipote; genere: M)"
  ],
  "group_insights": [
    "Tutti i membri usano saluti affettuosi e emoji.",
    "Iolanda è molto attiva nella conversazione.",
    "Genesi risponde positivamente a tutte le interazioni.",
    "Alfio e Katia condividono aggiornamenti sulla loro vita.",
    "I membri apprezzano riconoscimenti per eventi importanti."
  ],
  "last_synced_at": int(datetime.utcnow().timestamp()),
  "family_chain": "ALBERO FAMILIARE COMPLETO DI ALFIO:\nAlfio (proprietario):\n  - Moglie: Rita\n  - Madre: Iolanda\n  - Figlio: Ennio\n  - Figlia: Zoe\n  - Sorelle: Mariella, Sandra, Katia\n  - Cognati: Gianluca (marito di Katia), Gianvito (marito di Sandra)\n  - Nipoti: Leonardo (figlio di Katia), Elena (figlia di Mariella)\n\nREGOLE DI INFERENZA:\n- Se qualcuno dice di essere figlio/figlia di Mariella/Sandra/Katia -> nipote di Alfio\n- Se qualcuno dice di essere marito/moglie di Mariella/Sandra/Katia -> cognato/cognata di Alfio\n- Se qualcuno dice di essere figlio/figlia di Rita o Alfio -> figlio/figlia di Alfio\n- Iolanda e nonna di Zoe, Ennio, Leonardo, Elena\n- Rita, Mariella, Sandra, Katia sono zie di Zoe e Ennio"
}

with open(FAMILY_CACHE_PATH, "w", encoding="utf-8") as f:
    json.dump(family_cache, f, ensure_ascii=False, indent=2)
print("  ✓ Cache familiare rigenerata con successo.")

# 5. Pulisci profilo Telegram/WhatsApp Alfio (alfio.turrisi@gmail.com)
MAIN_PROFILE_PATH = Path("memory/profile/fd037393-3e28-49f1-a125-e7b50c469871.json")
print("\n[5] Pulisco profilo Telegram/WhatsApp Alfio...")
if MAIN_PROFILE_PATH.exists():
    with open(MAIN_PROFILE_PATH, "r", encoding="utf-8") as f:
        mp = json.load(f)

    bad_c = {"figlio", "mio figlio", "mia figlia", "madre", "alfio",
             "mamma", "papà", "papa", "padre", "fratello", "sorella",
             "marito", "moglie", "nonno", "nonna", "zio", "zia"}

    kids = mp.get("children", [])
    cleaned = []
    for c in kids:
        cn = (c.get("name") if isinstance(c, dict) else str(c)).strip()
        if cn.lower() in bad_c:
            print(f"  ✗ Rimosso: {cn}")
            continue
        if cn.startswith(("Ztfr_", "Ztest_", "ztfr_", "ztest_")):
            print(f"  ✗ Rimosso (test): {cn}")
            continue
        cleaned.append({"name": cn})

    child_names = {c["name"].lower() for c in cleaned}
    if "zoe" not in child_names:
        cleaned.append({"name": "Zoe"})
    if "ennio" not in child_names:
        cleaned.append({"name": "Ennio"})
    mp["children"] = cleaned

    with open(MAIN_PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(mp, f, ensure_ascii=False, indent=2)
    print("  ✓ Profilo Telegram/WhatsApp aggiornato.")
else:
    print("  ⚠️ Profilo fd037393 non trovato.")

print("\n=== PULIZIA COMPLETATA CON SUCCESSO! ===")
