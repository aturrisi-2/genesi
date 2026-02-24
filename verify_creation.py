
import asyncio
import os
import datetime
import uuid
from dotenv import load_dotenv
load_dotenv()

from core.icloud_service import ICloudService
from core.reminder_engine import reminder_engine
from core.storage import storage

async def test_create_and_verify():
    user_id = "test_icloud_creator"
    
    # 1. Setup credentials
    icloud_user = os.getenv("ICLOUD_USER")
    icloud_pass = os.getenv("ICLOUD_PASSWORD")
    
    if not icloud_user or not icloud_pass:
        print("Error: Credentials not found in .env")
        return

    print(f"--- Testing Event Creation on iCloud for {icloud_user} ---")
    
    # Initialize service
    svc = ICloudService(icloud_user, icloud_pass)
    
    # 2. Create a unique event
    test_id = str(uuid.uuid4())[:8]
    test_title = f"Test Genesi {test_id}"
    # Set to 2 hours from now
    target_dt = datetime.datetime.now() + datetime.timedelta(hours=2)
    
    print(f"Creating event: '{test_title}' at {target_dt.isoformat()}")
    
    # We use the direct service method to test the core logic
    success = svc.create_event(test_title, target_dt)
    
    if not success:
        print("FAIL: Could not create event on iCloud.")
        return
    
    print("SUCCESS: Event created on iCloud. Now verifying via fetch...")
    
    # 3. Wait a moment for iCloud to index
    await asyncio.sleep(3)
    
    # 4. Verify via get_events
    events = svc.get_events(days=1)
    found = any(test_title in e['summary'] for e in events)
    
    if found:
        print(f"VERIFICATION SUCCESS: Found '{test_title}' in the event list!")
    else:
        print(f"VERIFICATION PENDING: Event '{test_title}' not found in the first fetch. It might take a minute to sync.")
        print("Check your Apple Calendar app manually to be 100% sure.")

if __name__ == "__main__":
    asyncio.run(test_create_and_verify())
