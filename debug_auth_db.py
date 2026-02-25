
import asyncio
from sqlalchemy import select
from auth.database import async_session
from auth.models import AuthUser, AuthToken

async def check_user():
    async with async_session() as session:
        # Check users
        result = await session.execute(select(AuthUser))
        users = result.scalars().all()
        print(f"--- USERS ({len(users)}) ---")
        for u in users:
            print(f"ID: {u.id}, Email: {u.email}, Verified: {u.is_verified}, Admin: {u.is_admin}")
        
        # Check tokens
        result = await session.execute(select(AuthToken))
        tokens = result.scalars().all()
        print(f"\n--- TOKENS ({len(tokens)}) ---")
        for t in tokens:
            print(f"UserID: {t.user_id}, Type: {t.token_type}, Used: {t.used}")

if __name__ == "__main__":
    asyncio.run(check_user())
