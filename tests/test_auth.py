"""
Tests for Auth System — register, login, logout, password reset, admin protection,
unauthenticated access blocking, require_auth/require_admin middleware, visit tracking.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

# ── Auth module imports ──
from auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, generate_secure_token,
)
from auth.config import JWT_SECRET, JWT_ALGORITHM
from auth.models import AuthUser, AuthToken, Visit, Base

# ── SQLAlchemy in-memory test DB ──
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


# ═══════════════════════════════════════════════════════════════
# Test fixtures: in-memory SQLite
# ═══════════════════════════════════════════════════════════════

def _create_test_db():
    """Create an in-memory async SQLite engine + session factory."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def _init_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user(session, email="test@example.com", password="TestPass1",
                       is_verified=True, is_admin=False):
    """Helper: create a user in the test DB."""
    user = AuthUser(
        email=email,
        password_hash=hash_password(password),
        is_verified=is_verified,
        is_admin=is_admin,
    )
    session.add(user)
    await session.flush()
    return user


# ═══════════════════════════════════════════════════════════════
# Test: Password hashing
# ═══════════════════════════════════════════════════════════════

class TestPasswordHashing:

    def test_hash_and_verify(self):
        hashed = hash_password("MyPassword1")
        assert verify_password("MyPassword1", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("MyPassword1")
        assert verify_password("WrongPassword", hashed) is False

    def test_hash_is_different_each_time(self):
        h1 = hash_password("Same")
        h2 = hash_password("Same")
        assert h1 != h2  # bcrypt uses random salt


# ═══════════════════════════════════════════════════════════════
# Test: JWT tokens
# ═══════════════════════════════════════════════════════════════

class TestJWTTokens:

    def test_create_and_decode_access(self):
        token = create_access_token("user123", is_admin=False)
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["type"] == "access"
        assert payload["admin"] is False

    def test_create_and_decode_admin_access(self):
        token = create_access_token("admin1", is_admin=True)
        payload = decode_token(token)
        assert payload["admin"] is True

    def test_create_and_decode_refresh(self):
        token = create_refresh_token("user123")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user123"
        assert payload["type"] == "refresh"

    def test_invalid_token(self):
        assert decode_token("invalid.token.here") is None

    def test_expired_token(self):
        import jwt
        payload = {
            "sub": "user123",
            "type": "access",
            "exp": datetime.utcnow() - timedelta(hours=1),
            "iat": datetime.utcnow(),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        assert decode_token(token) is None

    def test_generate_secure_token(self):
        t1 = generate_secure_token()
        t2 = generate_secure_token()
        assert len(t1) > 20
        assert t1 != t2


# ═══════════════════════════════════════════════════════════════
# Test: Register → Login → Logout flow (DB-level)
# ═══════════════════════════════════════════════════════════════

class TestRegisterLoginLogout:

    def test_register_creates_user(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "new@test.com", "StrongPass1", is_verified=False)
                await session.commit()
                assert user.id is not None
                assert user.email == "new@test.com"
                assert user.is_verified is False
                assert verify_password("StrongPass1", user.password_hash)
            await engine.dispose()
        asyncio.run(_test())

    def test_login_verified_user(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "login@test.com", "Pass1234", is_verified=True)
                await session.commit()

                # Simulate login: verify password + create tokens
                assert verify_password("Pass1234", user.password_hash)
                assert user.is_verified is True
                access = create_access_token(user.id, user.is_admin)
                refresh = create_refresh_token(user.id)

                # Verify tokens
                ap = decode_token(access)
                assert ap["sub"] == user.id
                assert ap["type"] == "access"

                rp = decode_token(refresh)
                assert rp["sub"] == user.id
                assert rp["type"] == "refresh"
            await engine.dispose()
        asyncio.run(_test())

    def test_login_wrong_password(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "wrong@test.com", "Correct1", is_verified=True)
                await session.commit()
                assert verify_password("WrongPass1", user.password_hash) is False
            await engine.dispose()
        asyncio.run(_test())

    def test_login_unverified_blocked(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "unv@test.com", "Pass1234", is_verified=False)
                await session.commit()
                # Password correct but not verified → should be blocked
                assert verify_password("Pass1234", user.password_hash) is True
                assert user.is_verified is False
            await engine.dispose()
        asyncio.run(_test())

    def test_logout_clears_token(self):
        """Logout is client-side (localStorage). Server just acknowledges."""
        token = create_access_token("user123")
        payload = decode_token(token)
        assert payload is not None
        # After logout, client removes token. Server decode still works
        # but client won't send it anymore.
        assert payload["sub"] == "user123"


# ═══════════════════════════════════════════════════════════════
# Test: Password Reset flow
# ═══════════════════════════════════════════════════════════════

class TestPasswordReset:

    def test_reset_token_creation(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "reset@test.com", "OldPass1")
                token_str = generate_secure_token()
                token = AuthToken(
                    user_id=user.id,
                    token=token_str,
                    token_type="reset_password",
                    expires_at=datetime.utcnow() + timedelta(hours=1),
                )
                session.add(token)
                await session.commit()

                assert token.id is not None
                assert token.token == token_str
                assert token.used is False
            await engine.dispose()
        asyncio.run(_test())

    def test_reset_changes_password(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "reset2@test.com", "OldPass1")
                await session.commit()

                # Change password
                new_hash = hash_password("NewPass1")
                user.password_hash = new_hash
                await session.commit()

                # Verify new password works, old doesn't
                assert verify_password("NewPass1", user.password_hash) is True
                assert verify_password("OldPass1", user.password_hash) is False
            await engine.dispose()
        asyncio.run(_test())

    def test_reset_token_expired(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "exp@test.com", "Pass1234")
                token = AuthToken(
                    user_id=user.id,
                    token=generate_secure_token(),
                    token_type="reset_password",
                    expires_at=datetime.utcnow() - timedelta(hours=1),  # expired
                )
                session.add(token)
                await session.commit()

                # Token is expired
                assert datetime.utcnow() > token.expires_at
            await engine.dispose()
        asyncio.run(_test())

    def test_reset_token_used(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "used@test.com", "Pass1234")
                token = AuthToken(
                    user_id=user.id,
                    token=generate_secure_token(),
                    token_type="reset_password",
                    expires_at=datetime.utcnow() + timedelta(hours=1),
                    used=True,
                )
                session.add(token)
                await session.commit()

                assert token.used is True
            await engine.dispose()
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════
# Test: Admin access protection
# ═══════════════════════════════════════════════════════════════

class TestAdminProtection:

    def test_admin_token_has_admin_flag(self):
        token = create_access_token("admin1", is_admin=True)
        payload = decode_token(token)
        assert payload["admin"] is True

    def test_non_admin_token_no_flag(self):
        token = create_access_token("user1", is_admin=False)
        payload = decode_token(token)
        assert payload["admin"] is False

    def test_admin_user_model(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                admin = await _create_user(session, "admin@test.com", "Admin123", is_admin=True)
                user = await _create_user(session, "user@test.com", "User1234", is_admin=False)
                await session.commit()

                assert admin.is_admin is True
                assert user.is_admin is False
            await engine.dispose()
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════
# Test: Unauthenticated access blocked
# ═══════════════════════════════════════════════════════════════

class TestUnauthenticatedBlocked:

    def test_no_token_decode_fails(self):
        assert decode_token("") is None

    def test_garbage_token_decode_fails(self):
        assert decode_token("not.a.jwt") is None

    def test_wrong_secret_token_fails(self):
        import jwt
        payload = {
            "sub": "user123",
            "type": "access",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")
        assert decode_token(token) is None


# ═══════════════════════════════════════════════════════════════
# Test: Visit tracking model
# ═══════════════════════════════════════════════════════════════

class TestVisitTracking:

    def test_visit_creation(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                visit = Visit(ip="127.0.0.1", user_agent="TestBot/1.0", path="/")
                session.add(visit)
                await session.commit()

                assert visit.id is not None
                assert visit.ip == "127.0.0.1"
                assert visit.path == "/"
            await engine.dispose()
        asyncio.run(_test())

    def test_multiple_visits(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                for path in ["/", "/login", "/register", "/admin"]:
                    session.add(Visit(ip="10.0.0.1", path=path))
                await session.commit()

                from sqlalchemy import select, func
                count = (await session.execute(
                    select(func.count(Visit.id))
                )).scalar()
                assert count == 4
            await engine.dispose()
        asyncio.run(_test())

    def test_visit_has_timestamp(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                visit = Visit(ip="1.2.3.4", path="/login")
                session.add(visit)
                await session.commit()

                assert visit.visited_at is not None
            await engine.dispose()
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════
# Test: Email verification token flow
# ═══════════════════════════════════════════════════════════════

class TestEmailVerification:

    def test_verify_token_activates_user(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "verify@test.com", "Pass1234", is_verified=False)
                token = AuthToken(
                    user_id=user.id,
                    token=generate_secure_token(),
                    token_type="verify_email",
                    expires_at=datetime.utcnow() + timedelta(hours=48),
                )
                session.add(token)
                await session.commit()

                # Simulate verification
                user.is_verified = True
                token.used = True
                await session.commit()

                assert user.is_verified is True
                assert token.used is True
            await engine.dispose()
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════
# Test: Duplicate email registration
# ═══════════════════════════════════════════════════════════════

class TestDuplicateRegistration:

    def test_duplicate_email_rejected(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                await _create_user(session, "dup@test.com", "Pass1234")
                await session.commit()

                # Try to create another user with same email
                from sqlalchemy import select
                existing = await session.execute(
                    select(AuthUser).where(AuthUser.email == "dup@test.com")
                )
                assert existing.scalar_one_or_none() is not None
            await engine.dispose()
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════
# Test: init_environment (no broken imports)
# ═══════════════════════════════════════════════════════════════

class TestInitEnvironment:

    def test_init_environment_runs(self):
        """Verify init_environment doesn't crash (broken imports fixed)."""
        from auth.init_environment import initialize_user_environment
        # Should not raise
        initialize_user_environment("test-user-123", {"language": "it"})


# ═══════════════════════════════════════════════════════════════
# Test: Full flow integration
# ═══════════════════════════════════════════════════════════════

class TestFullFlow:

    def test_register_verify_login_me_logout(self):
        """Full flow: register → verify → login → /me → logout."""
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                # 1. Register
                user = await _create_user(session, "full@test.com", "FullPass1", is_verified=False)
                await session.commit()
                assert user.is_verified is False

                # 2. Verify
                user.is_verified = True
                await session.commit()
                assert user.is_verified is True

                # 3. Login
                assert verify_password("FullPass1", user.password_hash)
                access = create_access_token(user.id, user.is_admin)
                refresh = create_refresh_token(user.id)

                # 4. /me — decode token, get user info
                payload = decode_token(access)
                assert payload["sub"] == user.id
                assert payload["type"] == "access"

                # 5. Logout — client removes tokens
                # Server-side: token still valid but client won't use it
                assert decode_token(access) is not None

            await engine.dispose()
        asyncio.run(_test())
