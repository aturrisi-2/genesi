"""
tests/conftest.py — Fixture condivise per la test suite Genesi.
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── profili utente standard ──────────────────────────────────────────────────

@pytest.fixture
def test_user_id():
    return "test_user@genesi.test"


@pytest.fixture
def profile_full():
    return {
        "user_id": "test_user@genesi.test",
        "email": "test_user@genesi.test",
        "name": "Marco",
        "city": "Imola",
        "timezone": "Europe/Rome",
        "profession": "Architetto",
        "spouse": "Giulia",
        "pets": [{"type": "cane", "name": "Max"}],
        "children": [{"name": "Luca"}],
        "interests": ["musica", "calcio"],
        "traits": ["curioso"],
        "icloud_user": "marco@icloud.com",
        "icloud_password": "secret",
        "google_token": {"access_token": "tok_test", "refresh_token": "ref_test"},
    }


@pytest.fixture
def profile_minimal():
    return {
        "user_id": "test_user@genesi.test",
        "name": "Test",
        "city": "Roma",
        "timezone": "Europe/Rome",
    }


# ── brain_state dict-like (come passato a _handle_location, ecc.) ────────────

@pytest.fixture
def brain_state_dict(profile_full):
    return {
        "profile": profile_full,
        "relational_state": {"emotion": "neutro", "trust_level": 0.7},
        "episodic_memory": [],
    }


# ── latent state standard ────────────────────────────────────────────────────

@pytest.fixture
def latent_state_default():
    return {
        "synopsis": "stato neutro",
        "warmth": 0.6,
        "expand": 0.5,
        "evoc": 0.3,
        "ground": 0.7,
    }


# ── env senza chiavi API (sicuro per CI) ─────────────────────────────────────

@pytest.fixture(autouse=False)
def no_api_keys(monkeypatch):
    """Rimuove le API key reali per evitare chiamate accidentali a servizi esterni."""
    for var in [
        "OPENROUTER_API_KEY", "OPENAI_API_KEY",
        "OPENWEATHER_API_KEY", "GNEWS_API_KEY", "NEWSAPI_KEY",
        "PIXABAY_API_KEY",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
        "ICLOUD_USER", "ICLOUD_PASSWORD", "ICLOUD_PASS",
    ]:
        monkeypatch.delenv(var, raising=False)
