import os
import asyncio
from datetime import datetime, timedelta
from calendar_manager import calendar_manager
from core.log import log

async def test_calendar():
    print("🚀 Testing Unified Calendar...")
    
    # Test Local
    print("\n[1] Testing Local Reminder...")
    success = calendar_manager.add_event("Test Locale Genesi", datetime.now() + timedelta(minutes=1), provider='local')
    print(f"Local success: {success}")
    
    # Test Apple (will use credentials from .env)
    print("\n[2] Testing Apple iCloud Reminder...")
    # Using a future date to avoid immediate trigger
    test_date = datetime.now() + timedelta(days=1)
    success = calendar_manager.add_event("Test Apple Genesi", test_date, provider='apple')
    print(f"Apple success: {success}")

    # Test List
    print("\n[3] Listing Reminders...")
    rems = calendar_manager.list_reminders()
    print(f"Total reminders found: {len(rems)}")
    for r in rems:
        print(f" - [{r.get('provider')}] {r.get('summary') or r.get('text')} (Due: {r.get('due')})")

    # Test Async Check
    print("\n[4] Testing Async Check (Local)...")
    # Mark the first local one as due manually for test
    if calendar_manager.local_reminders:
        calendar_manager.local_reminders[0]['due'] = (datetime.now() - timedelta(seconds=1)).isoformat()
    
    due = await calendar_manager.check_async()
    print(f"Due events found: {len(due)}")
    for d in due:
        print(f" - TRIGGERED: {d['text']}")

if __name__ == "__main__":
    asyncio.run(test_calendar())
