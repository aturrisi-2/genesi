"""
Test di sicurezza — Meta Messaging (Facebook Messenger + Instagram DM)

Suite dedicata a scovare vulnerabilità nel canale webhook Meta:
- Bypass verifica firma HMAC (X-Hub-Signature-256)
- Bypass verify token (challenge GET)
- Injection nel sender ID (chiavi storage forgiate, path traversal)
- Replay attack (message-id duplicati)
- Loop infiniti (messaggi echo della pagina)
- Contaminazione cross-platform (payload instagram su endpoint messenger)
- Payload malformati / oversize
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hashlib
import hmac
import json
import pytest
from unittest.mock import AsyncMock, patch

import core.meta_messaging_bot as bot
from core.meta_messaging_bot import (
    verify_webhook, verify_signature, handle_update,
    _is_duplicate_mid, _SEEN_MIDS, MAX_TEXT_LEN,
)


# ═══════════════════════════════════════════════════════════════
# Verifica firma HMAC (X-Hub-Signature-256)
# ═══════════════════════════════════════════════════════════════

class TestSignatureVerification:

    def test_valid_signature_accepted(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "topsecret")
        body = b'{"object":"page","entry":[]}'
        sig = "sha256=" + hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
        assert verify_signature(body, sig) is True

    def test_invalid_signature_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "topsecret")
        body = b'{"object":"page","entry":[]}'
        assert verify_signature(body, "sha256=" + "0" * 64) is False

    def test_missing_signature_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "topsecret")
        assert verify_signature(b"{}", "") is False

    def test_wrong_prefix_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "topsecret")
        body = b"{}"
        digest = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
        # sha1 (algoritmo legacy) non deve essere accettato
        assert verify_signature(body, f"sha1={digest}") is False

    def test_tampered_body_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "topsecret")
        original = b'{"object":"page","entry":[]}'
        sig = "sha256=" + hmac.new(b"topsecret", original, hashlib.sha256).hexdigest()
        tampered = b'{"object":"page","entry":[{"evil":true}]}'
        assert verify_signature(tampered, sig) is False

    def test_dev_mode_without_secret_accepts(self, monkeypatch):
        # Senza app secret configurato (dev) accetta ma non deve crashare
        monkeypatch.setattr(bot, "META_APP_SECRET", "")
        assert verify_signature(b"{}", "") is True


# ═══════════════════════════════════════════════════════════════
# Verify token (challenge GET)
# ═══════════════════════════════════════════════════════════════

class TestWebhookVerifyToken:

    def test_correct_token_returns_challenge(self, monkeypatch):
        monkeypatch.setattr(bot, "META_VERIFY_TOKEN", "tok123")
        assert verify_webhook("subscribe", "tok123", "challenge-xyz") == "challenge-xyz"

    def test_wrong_token_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_VERIFY_TOKEN", "tok123")
        assert verify_webhook("subscribe", "WRONG", "challenge-xyz") is None

    def test_empty_token_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_VERIFY_TOKEN", "tok123")
        assert verify_webhook("subscribe", "", "challenge-xyz") is None

    def test_wrong_mode_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_VERIFY_TOKEN", "tok123")
        assert verify_webhook("unsubscribe", "tok123", "challenge-xyz") is None


# ═══════════════════════════════════════════════════════════════
# Sender ID injection (chiavi storage / path traversal)
# ═══════════════════════════════════════════════════════════════

def _payload(platform_object: str, sender_id: str, text: str = "ciao", mid: str = "") -> dict:
    return {
        "object": platform_object,
        "entry": [{
            "id": "page-1",
            "messaging": [{
                "sender": {"id": sender_id},
                "recipient": {"id": "page-1"},
                "message": {"mid": mid or f"mid.{sender_id}.{text[:8]}", "text": text},
            }],
        }],
    }


class TestSenderIdInjection:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("evil_id", [
        "../../etc/passwd",
        "123; rm -rf /",
        "abc' OR '1'='1",
        "123 456",
        "profile:altro_utente",
        "<script>alert(1)</script>",
        "ig_99999",            # tentativo di forgiare il namespace di un'altra piattaforma
        "9" * 40,              # oltre il limite di 32 cifre
        "",
    ])
    async def test_malicious_sender_ids_rejected(self, evil_id):
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text, \
             patch("core.meta_messaging_bot._handle_image", new_callable=AsyncMock) as mock_img:
            await handle_update(_payload("page", evil_id), "messenger")
            assert not mock_text.called, f"Sender id malevolo processato: {evil_id!r}"
            assert not mock_img.called

    @pytest.mark.asyncio
    async def test_valid_numeric_sender_accepted(self):
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(_payload("page", "1234567890123456", mid="mid.valid.1"), "messenger")
            assert mock_text.called
            # user_id deve avere il namespace messenger
            user_id = mock_text.call_args[0][0]
            assert user_id == "fb_1234567890123456"


# ═══════════════════════════════════════════════════════════════
# Replay attack (message-id duplicati)
# ═══════════════════════════════════════════════════════════════

class TestReplayProtection:

    def setup_method(self):
        _SEEN_MIDS.clear()

    def test_duplicate_mid_detected(self):
        assert _is_duplicate_mid("mid.AAA") is False
        assert _is_duplicate_mid("mid.AAA") is True

    def test_empty_mid_not_blocked(self):
        # mid vuoto non deve bloccare (Meta lo manda sempre, ma difensivo)
        assert _is_duplicate_mid("") is False
        assert _is_duplicate_mid("") is False

    def test_lru_bounded(self):
        for i in range(1000):
            _is_duplicate_mid(f"mid.{i}")
        assert len(_SEEN_MIDS) <= 500, "LRU mid non limitata: memoria illimitata = DoS"

    @pytest.mark.asyncio
    async def test_replayed_webhook_processed_once(self):
        _SEEN_MIDS.clear()
        payload = _payload("page", "111222333", mid="mid.replay.1")
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(payload, "messenger")
            await handle_update(payload, "messenger")  # replay identico
            assert mock_text.call_count == 1, "Replay non bloccato"


# ═══════════════════════════════════════════════════════════════
# Loop prevention (echo) ed eventi non-messaggio
# ═══════════════════════════════════════════════════════════════

class TestLoopPrevention:

    @pytest.mark.asyncio
    async def test_echo_message_ignored(self):
        payload = _payload("page", "1234567890", mid="mid.echo.1")
        payload["entry"][0]["messaging"][0]["message"]["is_echo"] = True
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(payload, "messenger")
            assert not mock_text.called, "Messaggio echo processato: rischio loop infinito"

    @pytest.mark.asyncio
    async def test_delivery_event_ignored(self):
        payload = {
            "object": "page",
            "entry": [{"messaging": [{
                "sender": {"id": "1234567890"},
                "delivery": {"mids": ["mid.x"], "watermark": 1},
            }]}],
        }
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(payload, "messenger")
            assert not mock_text.called


# ═══════════════════════════════════════════════════════════════
# Contaminazione cross-platform
# ═══════════════════════════════════════════════════════════════

class TestCrossPlatformIsolation:

    def setup_method(self):
        _SEEN_MIDS.clear()

    @pytest.mark.asyncio
    async def test_instagram_payload_on_messenger_endpoint_rejected(self):
        payload = _payload("instagram", "555666777", mid="mid.cross.1")
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(payload, "messenger")
            assert not mock_text.called, "Payload instagram processato come messenger"

    @pytest.mark.asyncio
    async def test_messenger_payload_on_instagram_endpoint_rejected(self):
        payload = _payload("page", "555666777", mid="mid.cross.2")
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(payload, "instagram")
            assert not mock_text.called

    @pytest.mark.asyncio
    async def test_namespaces_are_distinct(self):
        """Lo stesso sender id su piattaforme diverse produce user_id diversi."""
        seen_user_ids = []
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            mock_text.side_effect = lambda uid, *a, **k: seen_user_ids.append(uid)
            await handle_update(_payload("page", "42424242", mid="mid.ns.1"), "messenger")
            await handle_update(_payload("instagram", "42424242", mid="mid.ns.2"), "instagram")
        assert seen_user_ids == ["fb_42424242", "ig_42424242"]
        assert seen_user_ids[0] != seen_user_ids[1], \
            "Stesso user_id su piattaforme diverse: memorie contaminate"

    @pytest.mark.asyncio
    async def test_unknown_platform_rejected(self):
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(_payload("page", "123456", mid="mid.unk.1"), "telegram")
            assert not mock_text.called


# ═══════════════════════════════════════════════════════════════
# Payload malformati / oversize
# ═══════════════════════════════════════════════════════════════

class TestMalformedPayloads:

    def setup_method(self):
        _SEEN_MIDS.clear()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", [
        {},
        {"object": "page"},
        {"object": "page", "entry": "not-a-list"},
        {"object": "page", "entry": [{}]},
        {"object": "page", "entry": [{"messaging": [{}]}]},
        {"object": "page", "entry": [{"messaging": [{"sender": {}}]}]},
        {"object": "page", "entry": [{"messaging": [{"sender": {"id": "123"}, "message": None}]}]},
    ])
    async def test_malformed_payload_no_crash(self, payload):
        """Payload incompleti o corrotti non devono mai sollevare eccezioni."""
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock):
            await handle_update(payload, "messenger")  # non deve lanciare

    @pytest.mark.asyncio
    async def test_oversized_text_truncated(self):
        huge = "A" * (MAX_TEXT_LEN * 3)
        payload = _payload("page", "777888999", text=huge, mid="mid.big.1")
        with patch("core.meta_messaging_bot._handle_text", new_callable=AsyncMock) as mock_text:
            await handle_update(payload, "messenger")
            assert mock_text.called
            sent_text = mock_text.call_args[0][3]
            assert len(sent_text) <= MAX_TEXT_LEN, "Testo oversize non troncato (memory DoS)"


# ═══════════════════════════════════════════════════════════════
# Download media sicuro
# ═══════════════════════════════════════════════════════════════

class TestMediaDownloadSecurity:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", [
        "http://evil.example.com/img.jpg",        # no https
        "file:///etc/passwd",
        "ftp://example.com/x.jpg",
        "",
    ])
    async def test_non_https_rejected(self, url):
        from core.meta_messaging_bot import download_image
        data, mime = await download_image(url)
        assert data is None

    @pytest.mark.asyncio
    async def test_wrong_mime_rejected(self):
        from core.meta_messaging_bot import download_image

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "text/html; charset=utf-8"}
            content = b"<html>not an image</html>"

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url): return FakeResponse()

        with patch("core.meta_messaging_bot.httpx.AsyncClient", FakeClient):
            data, mime = await download_image("https://cdn.example.com/payload")
            assert data is None, "Content-type non immagine accettato"

    @pytest.mark.asyncio
    async def test_oversize_image_rejected(self):
        from core.meta_messaging_bot import download_image, MAX_IMAGE_BYTES

        class FakeResponse:
            status_code = 200
            headers = {"content-type": "image/jpeg"}
            content = b"x" * (MAX_IMAGE_BYTES + 1)

        class FakeClient:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def get(self, url): return FakeResponse()

        with patch("core.meta_messaging_bot.httpx.AsyncClient", FakeClient):
            data, mime = await download_image("https://cdn.example.com/huge.jpg")
            assert data is None, "Immagine oltre 20MB accettata (DoS)"


# ═══════════════════════════════════════════════════════════════
# Credenziali: mai hardcoded nel modulo
# ═══════════════════════════════════════════════════════════════

class TestNoHardcodedCredentials:

    def test_no_passwords_or_tokens_in_source(self):
        import inspect
        import core.meta_messaging_bot as mod
        source = inspect.getsource(mod)
        # Nessuna email/password hardcoded (pattern noti del progetto)
        assert "ZOEennio" not in source
        assert "@gmail.com" not in source
        # I token devono arrivare SOLO da os.getenv
        assert 'FB_PAGE_ACCESS_TOKEN", "")' in source or "os.getenv" in source

    def test_tokens_default_empty(self):
        # Se le env non sono configurate, i token sono stringhe vuote (no default segreti)
        import importlib
        with patch.dict(os.environ, {}, clear=False):
            for var in ("FB_PAGE_ACCESS_TOKEN", "IG_ACCESS_TOKEN", "META_APP_SECRET"):
                os.environ.pop(var, None)
            import core.meta_messaging_bot as mod
            importlib.reload(mod)
            assert mod.FB_PAGE_ACCESS_TOKEN == ""
            assert mod.IG_ACCESS_TOKEN == ""
            assert mod.META_APP_SECRET == ""


# ═══════════════════════════════════════════════════════════════
# Router: enforcement firma a livello endpoint
# ═══════════════════════════════════════════════════════════════

class _FakeRequest:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}

    async def body(self):
        return self._body


class TestRouterSignatureEnforcement:

    @pytest.mark.asyncio
    async def test_invalid_signature_returns_403_and_never_processes(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "topsecret")
        from api.meta_messaging import _receive
        body = json.dumps(_payload("page", "123456789", mid="mid.router.1")).encode()
        req = _FakeRequest(body, {"X-Hub-Signature-256": "sha256=" + "f" * 64})
        with patch("api.meta_messaging.handle_update", new_callable=AsyncMock) as mock_handle:
            res = await _receive(req, "messenger")
            assert getattr(res, "status_code", None) == 403
            assert not mock_handle.called, "Payload con firma invalida processato"

    @pytest.mark.asyncio
    async def test_valid_signature_processed(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "topsecret")
        from api.meta_messaging import _receive
        body = json.dumps(_payload("page", "123456789", mid="mid.router.2")).encode()
        sig = "sha256=" + hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
        req = _FakeRequest(body, {"X-Hub-Signature-256": sig})
        with patch("api.meta_messaging.handle_update", new_callable=AsyncMock) as mock_handle:
            res = await _receive(req, "messenger")
            assert res == {"status": "ok"}
            # handle_update parte come task: cedi il loop per farlo schedulare
            import asyncio as _aio
            await _aio.sleep(0)
            assert mock_handle.called

    @pytest.mark.asyncio
    async def test_invalid_json_returns_200_no_crash(self, monkeypatch):
        # Meta esige 200 anche su body corrotto, ma nulla deve essere processato
        monkeypatch.setattr(bot, "META_APP_SECRET", "")
        from api.meta_messaging import _receive
        req = _FakeRequest(b"not-json-{{{", {})
        with patch("api.meta_messaging.handle_update", new_callable=AsyncMock) as mock_handle:
            res = await _receive(req, "messenger")
            assert res == {"status": "ok"}
            assert not mock_handle.called

    @pytest.mark.asyncio
    async def test_json_array_payload_rejected(self, monkeypatch):
        monkeypatch.setattr(bot, "META_APP_SECRET", "")
        from api.meta_messaging import _receive
        req = _FakeRequest(b'["not", "a", "dict"]', {})
        with patch("api.meta_messaging.handle_update", new_callable=AsyncMock) as mock_handle:
            res = await _receive(req, "messenger")
            assert res == {"status": "ok"}
            assert not mock_handle.called


if __name__ == "__main__":
    import asyncio
    asyncio.run(pytest.main([__file__, "-v"]))
