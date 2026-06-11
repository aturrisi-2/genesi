#!/usr/bin/env python3
"""
🧠 GENESI DATA CLEANUP - Identity & Family Relationship Purge
Pulisce i record di memoria errati sul VPS in cui Sandra o altri membri
non-madri sono stati associati alla relazione "madre" / "mamma" di Alfio.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

from core.storage import storage

_OWNER_ID = "6028d92a-94f2-4e2f-bcb7-012c861e3ab2"  # Alfio
SANDRA_TELEGRAM_ID = "1329017213"

async def run_cleanup():
    print("=" * 80)
    print("🧼 SCRIPT DI PULIZIA IMPERSONIFICAZIONE E RELAZIONI ERRATE")
    print("=" * 80)

    modified_count = 0

    # 1. Pulisci il profilo principale di Alfio (Albero Familiare)
    profile_key = f"profile:{_OWNER_ID}"
    profile = await storage.load(profile_key, default={})
    if profile and "family_tree" in profile:
        tree = profile["family_tree"]
        keys_to_remove = []
        for key, info in list(tree.items()):
            name = info.get("name", "").lower()
            rel = info.get("relationship", "").lower()
            member_id = str(info.get("member_id", ""))
            
            # Sandra o ID specificato non devono essere segnati come madre/mamma
            if (member_id == SANDRA_TELEGRAM_ID or "sandra" in name) and rel in ("madre", "mamma"):
                print(f"📌 Trovata relazione errata nell'albero di Alfio: {info['name']} segnata come '{info['relationship']}'")
                keys_to_remove.append(key)
        
        if keys_to_remove:
            for k in keys_to_remove:
                del tree[k]
            profile["family_tree"] = tree
            await storage.save(profile_key, profile)
            print(f"   ✓ Profilo di Alfio aggiornato. Rimosse chiavi dell'albero: {keys_to_remove}")
            modified_count += 1
        else:
            print("   ℹ️ Nessuna relazione errata trovata nell'albero di Alfio.")

    # 2. Pulisci i personal_facts di Alfio
    pf_key = f"personal_facts:{_OWNER_ID}"
    pf_data = await storage.load(pf_key, default={"facts": []})
    if pf_data and "facts" in pf_data:
        facts = pf_data["facts"]
        original_len = len(facts)
        # Filtra via i fatti errati associati a Sandra o chiavi specifiche di madre errata
        cleaned_facts = []
        for fact in facts:
            key = fact.get("key", "")
            value = fact.get("value", "").lower()
            
            # Se la chiave riguarda "famiglia_madre" o "famiglia_mamma" e contiene Sandra o l'id di Sandra
            is_bad = False
            if key.startswith("famiglia_madre_") or key.startswith("famiglia_mamma_"):
                if SANDRA_TELEGRAM_ID in key or "sandra" in value:
                    is_bad = True
            
            if is_bad:
                print(f"📌 Trovato fatto personale errato in Alfio: {fact}")
            else:
                cleaned_facts.append(fact)
        
        if len(cleaned_facts) < original_len:
            pf_data["facts"] = cleaned_facts
            await storage.save(pf_key, pf_data)
            print(f"   ✓ Fatti personali di Alfio aggiornati. Rimosse {original_len - len(cleaned_facts)} righe errate.")
            modified_count += 1
        else:
            print("   ℹ️ Nessun fatto personale errato trovato per Alfio.")

    # 3. Pulisci il profilo di Sandra (telegram:group_member:1329017213)
    sandra_key = f"telegram:group_member:{SANDRA_TELEGRAM_ID}"
    sandra_member = await storage.load(sandra_key, default={})
    if sandra_member:
        rel = sandra_member.get("relationship_to_owner", "")
        facts = sandra_member.get("facts", {})
        
        changed = False
        if rel in ("madre", "mamma"):
            print(f"📌 Trovata relazione errata nel profilo membro di Sandra: relationship_to_owner='{rel}'")
            sandra_member["relationship_to_owner"] = ""
            changed = True
            
        if facts.get("relazione_con_alfio") in ("madre", "mamma"):
            print(f"📌 Trovato fatto errato nel profilo membro di Sandra: relazione_con_alfio='{facts['relazione_con_alfio']}'")
            facts["relazione_con_alfio"] = ""
            sandra_member["facts"] = facts
            changed = True
            
        if changed:
            await storage.save(sandra_key, sandra_member)
            print("   ✓ Profilo membro di Sandra ripulito con successo.")
            modified_count += 1
        else:
            print("   ℹ️ Il profilo membro di Sandra non aveva relazioni errate.")

    # 4. Pulisci il cache block della famiglia (telegram:family_members:owner)
    family_cache_key = f"telegram:family_members:{_OWNER_ID}"
    family_cache = await storage.load(family_cache_key, default={})
    if family_cache and "members" in family_cache:
        members = family_cache["members"]
        original_len = len(members)
        cleaned_members = []
        for m in members:
            # Esempio: "Sandra (relazione: madre; città: Siracusa)"
            if "sandra" in m.lower() and ("relazione: madre" in m.lower() or "relazione: mamma" in m.lower()):
                print(f"📌 Trovato membro errato in family_cache: '{m}'")
                # Sostituiamo o rimuoviamo la relazione errata
                new_m = m.replace("relazione: madre", "").replace("relazione: mamma", "").replace(" ;", "").replace("(; ", "(").replace("  ", " ").strip()
                cleaned_members.append(new_m)
            else:
                cleaned_members.append(m)
                
        if cleaned_members != members:
            family_cache["members"] = cleaned_members
            await storage.save(family_cache_key, family_cache)
            print("   ✓ Cache familiare aggiornata.")
            modified_count += 1
        else:
            print("   ℹ️ Nessuna relazione errata nella cache familiare.")

    print("=" * 80)
    print(f"🎉 PULIZIA COMPLETATA! Totale modifiche applicate: {modified_count}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_cleanup())
