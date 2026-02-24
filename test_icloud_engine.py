
import asyncio
import os
import datetime
from dotenv import load_dotenv
load_dotenv()

from core.reminder_engine import reminder_engine
from core.storage import storage

async def test_full_sync():
    user_id = "test_icloud_user"
    
    # 1. Setup profile with credentials from .env
    icloud_user = os.getenv("ICLOUD_USER")
    icloud_pass = os.getenv("ICLOUD_PASSWORD")
    
    if not icloud_user or not icloud_pass:
        print("Error: ICLOUD_USER or ICLOUD_PASSWORD not found in .env")
        return

    print(f"--- Simulating iCloud Sync for {user_id} ---")
    
    # Pre-save profile for the engine to find it
    await storage.save(f"profile:{user_id}", {
        "icloud_user": icloud_user,
        "icloud_password": icloud_pass,
        "name": "Tester"
    })
    
    # 2. Trigger Fetch
    print("Triggering fetch_icloud_reminders...")
    new_items = await reminder_engine.fetch_icloud_reminders(user_id, force=True)
    
    print(f"Sync complete. New items added: {len(new_items)}")
    for item in new_items:
        print(f"- {item['due']}: {item['text']}")
        
    # 3. Verify local storage
    all_rems = await reminder_engine.list_reminders(user_id)
    print(f"Total reminders in local storage for {user_id}: {len(all_rems)}")
    
    # 4. Check for past items in storage (should be zero if filtering worked)
    now_iso = datetime.datetime.now().isoformat()
    past_items = [r for r in all_rems if r.get('source') == 'icloud' and r.get('datetime', '') < now_iso]
    
    if past_items:
        print(f"FAIL: Found {len(past_items)} past iCloud items in local storage!")
        for p in past_items:
            print(f"  * {p['datetime']}: {p['text']}")
    else:
        print("SUCCESS: No past iCloud items found in storage.")

    # Cleanup (optional)
    # os.remove(f"data/reminders/{user_id}.json")

if __name__ == "__main__":
    asyncio.run(test_full_sync())
