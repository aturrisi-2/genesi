import asyncio
import sys
import os

# Add root folder to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.telegram_group_memory import get_member

async def main():
    print("=== DIAGNOSTICA HASH LID ===")
    jids = ['257955752587499', '111042101272800', '69123891531797']
    for j in jids:
        p_int = abs(hash(j)) % (10**9)
        m = await get_member(p_int)
        print(f"JID: {j} -> Hash Int: {p_int} -> Member Name: {m.get('first_name')}")

if __name__ == "__main__":
    asyncio.run(main())
