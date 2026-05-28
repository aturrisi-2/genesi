import asyncio
import os
import sys

# Aggiungi la root del progetto al path
sys.path.append(os.getcwd())

from core.storage import storage
from core.capability_tracker import capability_tracker

async def main():
    print("--- INIZIO ISPEZIONE MEMORIA ---")
    keys = await storage.list_keys("episodes")
    print(f"Chiavi trovate sotto 'episodes': {keys}")
    
    for key in keys:
        eps = await storage.load(f"episodes:{key}", default=[])
        profile = await storage.load(f"profile:{key}", default={})
        is_test = await capability_tracker._is_test_user(key)
        print(f"\nUser/Chat ID: {key}")
        print(f"  - Numero episodi: {len(eps)}")
        print(f"  - Profilo associato: {profile}")
        print(f"  - È utente di test? {is_test}")
        if eps:
            print(f"  - Ultimo episodio salvato il: {eps[-1].get('saved_at', 'N/D')}")
            print(f"  - Testo ultimo episodio: {eps[-1].get('text', '')[:100]}")
            
    print("\n--- METRICHE CORRENTI ---")
    metrics = await capability_tracker.compute_current()
    print(f"Scores calcolati: {metrics.get('scores', {})}")
    print("--- FINE ISPEZIONE ---")

if __name__ == "__main__":
    asyncio.run(main())
