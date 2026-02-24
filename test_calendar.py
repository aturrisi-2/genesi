import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Path setup
sys.path.append(str(Path(__file__).parent))

# Load env (ensure real or dummy creds are present)
load_dotenv()

from calendar_manager import calendar_manager
from core.proactor import proactor

async def test_apple_event():
    print("\n--- Testing Apple/iCloud Event ---")
    title = "Test Apple Event " + datetime.now().strftime("%H:%M:%S")
    dt = datetime.now() + timedelta(days=1)
    
    # Direct manager call
    success = calendar_manager.add_event(title, dt, provider='apple')
    print(f"Apple direct add success: {success}")
    
    # Proactor call
    response = await proactor.handle("test_user", f"/cal add {title} domani alle 15")
    print(f"Proactor response: {response}")

async def test_google_event():
    print("\n--- Testing Google Event ---")
    title = "Test Google Event " + datetime.now().strftime("%H:%M:%S")
    dt = datetime.now() + timedelta(days=2)
    
    # Direct manager call
    success = calendar_manager.add_event(title, dt, provider='google')
    print(f"Google direct add success: {success}")
    
    # Proactor call
    response = await proactor.handle("test_user", "sincronizza google")
    print(f"Proactor sync response: {response}")

async def test_local_event_and_scheduler():
    print("\n--- Testing Local Event and Scheduler ---")
    title = "Test Local Event Fast"
    # Set to 1 second from now to trigger quickly
    dt = datetime.now() + timedelta(seconds=2)
    
    calendar_manager.add_event(title, dt, provider='local')
    print("Local event added. Waiting 3 seconds...")
    await asyncio.sleep(3)
    
    due = await calendar_manager.check_async()
    if due:
        print(f"SUCCESS: Triggered {len(due)} reminders")
        for r in due:
            print(f" - {r['text']}")
    else:
        print("FAILURE: No reminders triggered")

async def run_all_tests():
    # Apple test might fail if no creds, but we check if it handles it
    try:
        await test_apple_event()
    except Exception as e:
        print(f"Apple test error: {e}")
        
    try:
        await test_google_event()
    except Exception as e:
        print(f"Google test error: {e}")
        
    await test_local_event_and_scheduler()

if __name__ == "__main__":
    asyncio.run(run_all_tests())
