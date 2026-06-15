import asyncio
from sqlalchemy import select

from auth.database import async_session
from auth.models import AuthUser
from auth.security import hash_password


EMAIL = "idappleturrisi@gmail.com"
NEW_PASSWORD = "Genesi123!"


async def reset_password():
    async with async_session() as session:
        result = await session.execute(
            select(AuthUser).where(AuthUser.email == EMAIL)
        )
        user = result.scalar_one_or_none()

        if user:
            user.password_hash = hash_password(NEW_PASSWORD)
            await session.commit()
            print("✅ Password aggiornata con successo.")
        else:
            print("❌ Utente non trovato.")


if __name__ == "__main__":
    asyncio.run(reset_password())
