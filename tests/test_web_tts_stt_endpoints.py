from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

import api.stt as stt_api
import tts.tts_api as tts_api


class _FakeTTSProvider:
    def __init__(self, audio: bytes = b"RIFFfake-wav-bytes", name: str = "piper"):
        self.audio = audio
        self._name = name
        self.calls = []

    async def synthesize(self, text: str):
        self.calls.append(text)
        return self.audio

    def name(self) -> str:
        return self._name


class _FailingTTSProvider:
    async def synthesize(self, text: str):
        raise RuntimeError("mock tts provider failed")

    def name(self) -> str:
        return "mock"


class _FakeChatMemory:
    def get_last_message(self, _user_id):
        return {"intent": "chat_free"}


def _test_user():
    return SimpleNamespace(id="test-user", user_id="test-user", email="test@example.com")


def _app_with_routers(authenticated: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(tts_api.router, prefix="/api")
    app.include_router(stt_api.router, prefix="/api")
    if authenticated:
        app.dependency_overrides[tts_api.require_auth] = _test_user
        app.dependency_overrides[stt_api.require_auth] = _test_user
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_tts_endpoint_requires_auth():
    app = _app_with_routers(authenticated=False)

    async with _client(app) as client:
        response = await client.post("/api/tts/", json={"text": "ciao"})

    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_tts_endpoint_streams_mocked_audio(monkeypatch):
    provider = _FakeTTSProvider(audio=b"RIFFmock-audio", name="piper")

    monkeypatch.setattr("core.chat_memory.ChatMemory", lambda: _FakeChatMemory())
    monkeypatch.setattr("core.tts_provider.get_tts_provider_for_intent", lambda **_kwargs: provider)

    app = _app_with_routers(authenticated=True)

    async with _client(app) as client:
        response = await client.post("/api/tts/", json={"text": "Ciao mondo"})

    assert response.status_code == 200
    assert response.content == b"RIFFmock-audio"
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.headers["content-length"] == str(len(b"RIFFmock-audio"))
    assert provider.calls == ["Ciao mondo"]


@pytest.mark.asyncio
async def test_tts_endpoint_rejects_missing_text_with_validation_error():
    app = _app_with_routers(authenticated=True)

    async with _client(app) as client:
        response = await client.post("/api/tts/", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_tts_endpoint_provider_failure_is_controlled(monkeypatch):
    monkeypatch.setattr("core.chat_memory.ChatMemory", lambda: _FakeChatMemory())
    monkeypatch.setattr("core.tts_provider.get_tts_provider_for_intent", lambda **_kwargs: _FailingTTSProvider())

    app = _app_with_routers(authenticated=True)

    async with _client(app) as client:
        response = await client.post("/api/tts/", json={"text": "Ciao"})

    assert response.status_code == 500
    assert "TTS error" in response.text
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_stt_endpoint_requires_auth():
    app = _app_with_routers(authenticated=False)

    async with _client(app) as client:
        response = await client.post(
            "/api/stt/",
            files={"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code in {401, 403}


@pytest.mark.asyncio
async def test_stt_endpoint_returns_mocked_transcription(monkeypatch):
    calls = []

    async def fake_transcribe(audio_data: bytes, content_type: str, filename: str = "audio"):
        calls.append((audio_data, content_type, filename))
        return {"text": "ciao trascritto", "stt_status": "ok"}

    monkeypatch.setattr(stt_api, "transcribe_audio", fake_transcribe)
    app = _app_with_routers(authenticated=True)

    async with _client(app) as client:
        response = await client.post(
            "/api/stt/",
            files={"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code == 200
    assert response.json() == {"text": "ciao trascritto", "stt_status": "ok"}
    assert calls == [(b"fake-audio-bytes", "audio/webm", "rec.webm")]


@pytest.mark.asyncio
async def test_stt_endpoint_rejects_missing_audio_field():
    app = _app_with_routers(authenticated=True)

    async with _client(app) as client:
        response = await client.post(
            "/api/stt/",
            files={"wrong": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_stt_endpoint_transcriber_failure_is_controlled(monkeypatch):
    async def fake_transcribe(_audio_data: bytes, _content_type: str, filename: str = "audio"):
        return {"text": "", "stt_status": "error", "error": "mock stt provider failed"}

    monkeypatch.setattr(stt_api, "transcribe_audio", fake_transcribe)
    app = _app_with_routers(authenticated=True)

    async with _client(app) as client:
        response = await client.post(
            "/api/stt/",
            files={"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code == 200
    assert response.json()["stt_status"] == "error"
    assert "mock stt provider failed" in response.json()["error"]
    assert "Traceback" not in response.text


def test_web_tts_stt_endpoint_modules_do_not_import_group_bridges():
    for module in ("tts/tts_api.py", "api/stt.py"):
        src = open(module, "r", encoding="utf-8").read().lower()
        assert "baileys" not in src
        assert "whatsapp" not in src
        assert "telegram" not in src
