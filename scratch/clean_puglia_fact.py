import json
import os

def clean_facts():
    files_to_clean = [
        "/opt/genesi/memory/personal_facts/-318483633.json",
        "/opt/genesi/memory/personal_facts/bd8d24fa-f956-448c-9fca-b02043aaca18.json"
    ]

    for filepath in files_to_clean:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            original_len = len(data.get("facts", []))
            # Rimuovi il fatto sulla Puglia obsoleta
            data["facts"] = [f for f in data.get("facts", []) if f.get("key") != "sandra_in_puglia"]
            new_len = len(data["facts"])

            if original_len != new_len:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                print(f"Pulito {filepath}: rimosso fatto Puglia obsoleta.")
            else:
                print(f"Nessun fatto Puglia obsoleta in {filepath}.")

    # Aggiorna il profilo di Sandra per riflettere Bracciano come città attuale
    sandra_profile_path = "/opt/genesi/memory/telegram/group_member:1329017213.json"
    if os.path.exists(sandra_profile_path):
        with open(sandra_profile_path, "r", encoding="utf-8") as f:
            member = json.load(f)
        
        member["city"] = "Bracciano"
        if "facts" not in member:
            member["facts"] = {}
        member["facts"]["city"] = "Bracciano"
        
        with open(sandra_profile_path, "w", encoding="utf-8") as f:
            json.dump(member, f, ensure_ascii=False, indent=2)
        print(f"Aggiornata città di Sandra in {sandra_profile_path} a Bracciano.")

if __name__ == "__main__":
    clean_facts()
