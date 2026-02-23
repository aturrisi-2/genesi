from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select
from auth.config import DATABASE_URL
from auth.models import Base, AuthUser

engine = create_async_engine(
    DATABASE_URL, 
    echo=False,
    connect_args={"timeout": 30}
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    import asyncio
    from sqlalchemy import text
    retries = 10
    while retries > 0:
        try:
            async with engine.begin() as conn:
                # Impostiamo il timeout anche via PRAGMA per sicurezza
                await conn.execute(text("PRAGMA busy_timeout = 30000"))
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as e:
            if "locked" in str(e).lower() and retries > 1:
                print(f"[DB] Database locked, waiting for release... ({retries-1} left)")
                await asyncio.sleep(3)
                retries -= 1
            else:
                raise e


async def get_db() -> AsyncSession:
    async with async_session() as session:
        print(f"[DEBUG AUTH] DB URL: {engine.url}")  # DEBUG TEMPORANEO
        yield session


async def get_user_by_id(user_id: str) -> AuthUser:
    """Ottiene utente per ID dal database."""
    async with async_session() as session:
        result = await session.execute(select(AuthUser).where(AuthUser.id == user_id))
        return result.scalar_one_or_none()
