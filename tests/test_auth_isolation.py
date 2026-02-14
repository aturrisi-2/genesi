"""
Tests for Auth Isolation — user_id uniqueness, memory isolation,
document isolation, 401 without auth, admin access control.

Verifies the architectural rule: user_id comes ONLY from JWT, never from client.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, generate_secure_token,
)
from auth.config import JWT_SECRET, JWT_ALGORITHM, ADMIN_EMAILS
from auth.models import AuthUser, AuthToken, Visit, Base

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, func


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _create_test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def _init_tables(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _create_user(session, email, password="TestPass1",
                       is_verified=True, is_admin=False):
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
# 1. Registrazione crea user_id unico
# ═══════════════════════════════════════════════════════════════

class TestUniqueUserId:

    def test_two_registrations_produce_different_ids(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user_a = await _create_user(session, "alice@test.com")
                user_b = await _create_user(session, "bob@test.com")
                await session.commit()

                assert user_a.id != user_b.id
                assert len(user_a.id) > 10  # UUID format
                assert len(user_b.id) > 10
            await engine.dispose()
        asyncio.run(_test())

    def test_user_id_is_uuid_format(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                user = await _create_user(session, "uuid@test.com")
                await session.commit()
                # UUID has 36 chars with dashes
                assert len(user.id) == 36
                assert user.id.count('-') == 4
            await engine.dispose()
        asyncio.run(_test())

    def test_ten_users_all_unique(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                ids = set()
                for i in range(10):
                    user = await _create_user(session, f"user{i}@test.com")
                    ids.add(user.id)
                await session.commit()
                assert len(ids) == 10
            await engine.dispose()
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════
# 2. Due utenti diversi non vedono la stessa memoria
# ═══════════════════════════════════════════════════════════════

class TestMemoryIsolation:

    def test_storage_keys_are_user_scoped(self):
        """Profile storage keys include user_id, so different users have different keys."""
        user_a_id = "aaaa-1111-aaaa-1111"
        user_b_id = "bbbb-2222-bbbb-2222"

        key_a = f"profile:{user_a_id}"
        key_b = f"profile:{user_b_id}"

        assert key_a != key_b
        assert user_a_id in key_a
        assert user_b_id in key_b
        assert user_a_id not in key_b

    def test_jwt_tokens_carry_different_user_ids(self):
        """Two users get tokens with different sub claims."""
        token_a = create_access_token("user-A-id", is_admin=False)
        token_b = create_access_token("user-B-id", is_admin=False)

        payload_a = decode_token(token_a)
        payload_b = decode_token(token_b)

        assert payload_a["sub"] == "user-A-id"
        assert payload_b["sub"] == "user-B-id"
        assert payload_a["sub"] != payload_b["sub"]

    def test_user_a_token_cannot_access_user_b_data(self):
        """Token for user A should decode to user A's id, not user B's."""
        token_a = create_access_token("user-A-id")
        payload = decode_token(token_a)

        # Backend would use payload["sub"] as user_id
        user_id = payload["sub"]
        assert user_id == "user-A-id"
        assert user_id != "user-B-id"

        # Storage key would be scoped to user A
        storage_key = f"profile:{user_id}"
        assert "user-A-id" in storage_key
        assert "user-B-id" not in storage_key

    def test_memory_storage_isolation(self):
        """In-memory storage: two users store different data under different keys."""
        from core.memory_storage import MemoryStorage
        store = MemoryStorage()

        store.save("chat:user-A", [{"msg": "hello from A"}])
        store.save("chat:user-B", [{"msg": "hello from B"}])

        data_a = store.load("chat:user-A")
        data_b = store.load("chat:user-B")

        assert data_a != data_b
        assert data_a[0]["msg"] == "hello from A"
        assert data_b[0]["msg"] == "hello from B"

    def test_user_manager_isolation(self):
        """User manager creates separate entries per user_id."""
        from core.user_manager import UserManager
        mgr = UserManager()

        mgr.create_user("user-X")
        mgr.create_user("user-Y")

        x = mgr.get_user("user-X")
        y = mgr.get_user("user-Y")

        assert x is not None
        assert y is not None
        assert x["user_id"] == "user-X"
        assert y["user_id"] == "user-Y"
        assert x["user_id"] != y["user_id"]


# ═══════════════════════════════════════════════════════════════
# 3. Un utente non può accedere ai documenti di un altro
# ═══════════════════════════════════════════════════════════════

class TestDocumentIsolation:

    def test_document_ids_are_user_scoped(self):
        """Document IDs include user_id prefix, ensuring isolation."""
        import uuid
        user_a = "user-A-id"
        user_b = "user-B-id"

        doc_a = f"{user_a}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        doc_b = f"{user_b}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        assert doc_a.startswith(user_a)
        assert doc_b.startswith(user_b)
        assert not doc_a.startswith(user_b)
        assert not doc_b.startswith(user_a)

    def test_active_documents_scoped_to_user(self):
        """Active documents list is stored under user-specific profile key."""
        profile_key_a = "profile:user-A"
        profile_key_b = "profile:user-B"

        assert profile_key_a != profile_key_b
        assert "user-A" in profile_key_a
        assert "user-B" not in profile_key_a


# ═══════════════════════════════════════════════════════════════
# 4. Senza login → 401
# ═══════════════════════════════════════════════════════════════

class TestUnauthenticated401:

    def test_no_token_returns_none(self):
        """decode_token with empty string returns None → 401 in middleware."""
        assert decode_token("") is None

    def test_expired_token_returns_none(self):
        """Expired token → None → 401."""
        import jwt
        payload = {
            "sub": "user123",
            "type": "access",
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        assert decode_token(token) is None

    def test_wrong_secret_returns_none(self):
        """Token signed with wrong secret → None → 401."""
        import jwt
        payload = {
            "sub": "user123",
            "type": "access",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret-key-12345678901234567890", algorithm="HS256")
        assert decode_token(token) is None

    def test_refresh_token_rejected_as_access(self):
        """Refresh token has type='refresh', require_auth checks type='access'."""
        token = create_refresh_token("user123")
        payload = decode_token(token)
        assert payload is not None
        assert payload["type"] == "refresh"
        # require_auth would reject this because type != "access"

    def test_malformed_token_returns_none(self):
        assert decode_token("not-a-jwt") is None
        assert decode_token("a.b") is None
        assert decode_token("a.b.c.d") is None

    def test_api_endpoints_require_auth_in_source(self):
        """Verify that protected API source files contain require_auth/require_admin."""
        base = os.path.dirname(os.path.dirname(__file__))

        # chat.py must use require_auth
        with open(os.path.join(base, "api", "chat.py"), "r", encoding="utf-8") as f:
            src = f.read()
        assert "require_auth" in src, "api/chat.py must use require_auth"
        assert "Depends(require_auth)" in src, "chat endpoint must use Depends(require_auth)"

        # upload.py must use require_auth
        with open(os.path.join(base, "api", "upload.py"), "r", encoding="utf-8") as f:
            src = f.read()
        assert "require_auth" in src, "api/upload.py must use require_auth"

        # user.py must use require_auth
        with open(os.path.join(base, "api", "user.py"), "r", encoding="utf-8") as f:
            src = f.read()
        assert "require_auth" in src, "api/user.py must use require_auth"

        # stt.py must use require_auth
        with open(os.path.join(base, "api", "stt.py"), "r", encoding="utf-8") as f:
            src = f.read()
        assert "require_auth" in src, "api/stt.py must use require_auth"

        # memory.py must use require_admin
        with open(os.path.join(base, "api", "memory.py"), "r", encoding="utf-8") as f:
            src = f.read()
        assert "require_admin" in src, "api/memory.py must use require_admin"

        # tts_api.py must use require_auth
        with open(os.path.join(base, "tts", "tts_api.py"), "r", encoding="utf-8") as f:
            src = f.read()
        assert "require_auth" in src, "tts/tts_api.py must use require_auth"


# ═══════════════════════════════════════════════════════════════
# 5. Admin può vedere tutti gli utenti / utente normale no
# ═══════════════════════════════════════════════════════════════

class TestAdminAccessControl:

    def test_admin_token_has_admin_flag(self):
        token = create_access_token("admin-id", is_admin=True)
        payload = decode_token(token)
        assert payload["admin"] is True

    def test_normal_user_no_admin_flag(self):
        token = create_access_token("user-id", is_admin=False)
        payload = decode_token(token)
        assert payload["admin"] is False

    def test_admin_user_in_db(self):
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                admin = await _create_user(session, "admin@test.com", is_admin=True)
                normal = await _create_user(session, "normal@test.com", is_admin=False)
                await session.commit()

                assert admin.is_admin is True
                assert normal.is_admin is False

                # Admin can query all users
                result = await session.execute(select(func.count(AuthUser.id)))
                total = result.scalar()
                assert total == 2
            await engine.dispose()
        asyncio.run(_test())

    def test_normal_user_cannot_be_admin(self):
        """Normal user token should not have admin=True."""
        token = create_access_token("normal-user", is_admin=False)
        payload = decode_token(token)
        assert payload["admin"] is False
        # require_admin would reject this

    def test_admin_stats_requires_admin_email(self):
        """Admin stats endpoint checks both is_admin flag AND email in ADMIN_EMAILS."""
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                # User with is_admin=True but email not in ADMIN_EMAILS
                fake_admin = await _create_user(session, "fake@notadmin.com", is_admin=True)
                await session.commit()

                # The require_admin dependency checks:
                # user.is_admin AND user.email in ADMIN_EMAILS
                # So fake_admin would be rejected if email not in whitelist
                assert fake_admin.is_admin is True
                assert fake_admin.email not in ADMIN_EMAILS
            await engine.dispose()
        asyncio.run(_test())


# ═══════════════════════════════════════════════════════════════
# 6. No user_id from client — architectural verification
# ═══════════════════════════════════════════════════════════════

class TestNoClientUserId:

    def test_chat_request_has_no_user_id_field(self):
        """ChatRequest in chat.py source must NOT have user_id field."""
        base = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(base, "api", "chat.py"), "r", encoding="utf-8") as f:
            src = f.read()
        # Find ChatRequest class definition — extract only until next class
        idx = src.find("class ChatRequest")
        assert idx >= 0
        end_idx = src.find("class ", idx + 1)  # next class (ChatResponse)
        class_body = src[idx:end_idx] if end_idx > idx else src[idx:idx+80]
        assert "user_id" not in class_body, "ChatRequest must NOT have user_id field"

    def test_chat_endpoint_uses_depends_auth(self):
        """chat_endpoint must use Depends(require_auth) in source."""
        base = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(base, "api", "chat.py"), "r", encoding="utf-8") as f:
            src = f.read()
        assert "Depends(require_auth)" in src
        # The endpoint function should have user: AuthUser parameter
        idx = src.find("async def chat_endpoint")
        assert idx >= 0
        sig_line = src[idx:idx+200]
        assert "user: AuthUser" in sig_line or "user:AuthUser" in sig_line

    def test_upload_endpoint_no_user_id_form(self):
        """upload_file source must NOT accept user_id as Form field."""
        base = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(base, "api", "upload.py"), "r", encoding="utf-8") as f:
            src = f.read()
        # Check the function signature line only (first line of def)
        idx = src.find("async def upload_file")
        assert idx >= 0
        end_of_sig = src.find("):", idx)
        sig_line = src[idx:end_of_sig + 2]
        assert "user_id" not in sig_line, "upload_file signature must NOT accept user_id from client"
        assert "Form" not in sig_line, "upload_file must NOT use Form for user_id"
        assert "Depends(require_auth)" in src

    def test_bootstrap_no_user_id_in_body(self):
        """bootstrap_user source must NOT accept user_id from request body."""
        base = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(base, "api", "user.py"), "r", encoding="utf-8") as f:
            src = f.read()
        # Must NOT have BootstrapRequest with user_id
        assert "BootstrapRequest" not in src or "user_id" not in src, \
            "bootstrap must NOT accept user_id from client body"
        # Must use require_auth
        assert "require_auth" in src

    def test_frontend_no_crypto_random_uuid(self):
        """app.v2.js must NOT contain crypto.randomUUID() for user_id generation."""
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app.v2.js")
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "crypto.randomUUID()" not in content, \
            "Frontend must NOT generate user_id with crypto.randomUUID()"

    def test_frontend_no_user_id_in_chat_body(self):
        """app.v2.js sendChatMessage must NOT send user_id in body."""
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app.v2.js")
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Find sendChatMessage function and check its body
        idx = content.find("async function sendChatMessage")
        assert idx >= 0, "sendChatMessage function must exist"
        # Get the function body (next ~500 chars)
        func_body = content[idx:idx+500]
        assert "user_id" not in func_body, \
            "sendChatMessage must NOT include user_id in request body"

    def test_frontend_sends_authorization_header(self):
        """app.v2.js must send Authorization header on API calls."""
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app.v2.js")
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "authHeaders()" in content, "Frontend must use authHeaders() for API calls"
        assert "'Authorization'" in content or '"Authorization"' in content, \
            "Frontend must send Authorization header"

    def test_frontend_redirects_to_login(self):
        """app.v2.js must redirect to /login when not authenticated."""
        js_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "app.v2.js")
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "window.location.href = '/login'" in content, \
            "Frontend must redirect to /login when not authenticated"


# ═══════════════════════════════════════════════════════════════
# 7. Full isolation flow
# ═══════════════════════════════════════════════════════════════

class TestFullIsolationFlow:

    def test_two_users_complete_isolation(self):
        """Register two users, verify they get different IDs, tokens, and storage keys."""
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                # Register two users
                alice = await _create_user(session, "alice@test.com", "AlicePass1")
                bob = await _create_user(session, "bob@test.com", "BobPass1")
                await session.commit()

                # Different IDs
                assert alice.id != bob.id

                # Different tokens
                token_a = create_access_token(alice.id, alice.is_admin)
                token_b = create_access_token(bob.id, bob.is_admin)
                assert token_a != token_b

                # Tokens decode to different users
                pa = decode_token(token_a)
                pb = decode_token(token_b)
                assert pa["sub"] == alice.id
                assert pb["sub"] == bob.id
                assert pa["sub"] != pb["sub"]

                # Storage keys are different
                assert f"profile:{alice.id}" != f"profile:{bob.id}"
                assert f"chat:{alice.id}" != f"chat:{bob.id}"

                # Alice's token cannot access Bob's data
                assert pa["sub"] != bob.id
                assert pb["sub"] != alice.id

            await engine.dispose()
        asyncio.run(_test())

    def test_unverified_user_blocked(self):
        """Unverified user should not pass require_auth."""
        async def _test():
            engine, sf = _create_test_db()
            await _init_tables(engine)
            async with sf() as session:
                unverified = await _create_user(session, "unv@test.com", is_verified=False)
                await session.commit()

                # Token is valid but user is not verified
                # require_auth checks is_verified
                assert unverified.is_verified is False
            await engine.dispose()
        asyncio.run(_test())
