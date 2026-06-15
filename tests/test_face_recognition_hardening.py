"""
tests/test_face_recognition_hardening.py

Blindatura del sistema di riconoscimento volti/animali — invarianti cross-platform.
Locka i fix della sessione 2026-06-15 per prevenire regressioni:

- BUG#2  : una sessione awaiting per foto (chiave coerente set↔lookup)
- remaining/all_done corretti anche al primo testo senza nomi (fallback)
- #B     : re-ask quando l'utente CHIEDE chi sono invece di rispondere
- #3     : auto-riferimento "sono io" → nome speaker (no nome random)
- TTL    : finestra awaiting 30 min

I test NON dipendono da torch/modelli/llm: face_memory_service ha import top
leggeri. storage e l'estrazione LLM sono mockati.
"""
import time
import importlib
import pytest


# ── Fake storage in-memory (sostituisce core.storage.storage) ────────────────
class _FakeStorage:
    def __init__(self):
        self.kv = {}

    async def load(self, key, default=None):
        return self.kv.get(key, default)

    async def save(self, key, val):
        self.kv[key] = val

    async def delete(self, key):
        self.kv.pop(key, None)


@pytest.fixture
def fms(monkeypatch):
    """Importa face_memory_service con storage mockato."""
    import core.storage as storage_mod
    fake = _FakeStorage()
    monkeypatch.setattr(storage_mod, "storage", fake)
    fms = importlib.import_module("core.face_memory_service")
    return fms, fake


# ── _is_identity_question (#B): distingue domanda da nomi ─────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Conosci chi sono i soggetti in foto?", True),
    ("Chi sono le persone nell'immagine?", True),
    ("Riconosci chi c'è in foto?", True),
    ("da sinistra Mariella, Rita, Zoe", False),   # nomi, non domanda
    ("Quella a destra è Iolanda", False),
    ("Che tempo fa oggi?", False),                # non correlato
    ("", False),
])
def test_is_identity_question(fms, text, expected):
    mod, _ = fms
    assert mod._is_identity_question(text) is expected


# ── awaiting: chiave coerente set↔get + roundtrip ────────────────────────────

@pytest.mark.asyncio
async def test_awaiting_set_get_same_key(fms):
    mod, fake = fms
    await mod.set_awaiting_faces("sess-123", "/tmp/x.jpg", "[TOTAL_HUMANS:3]", unknown_count=3)
    # La chiave usata è platform-agnostica e deterministica
    assert "short_term_chat:awaiting_faces_sess-123" in fake.kv
    got = await mod.get_awaiting_faces("sess-123")
    assert got is not None
    assert got["unknown_count"] == 3
    assert got["identified"] == []


@pytest.mark.asyncio
async def test_awaiting_ttl_expiry(fms):
    mod, fake = fms
    await mod.set_awaiting_faces("sess-ttl", "/tmp/x.jpg", "desc", unknown_count=1)
    # Forza timestamp oltre la finestra TTL
    key = "short_term_chat:awaiting_faces_sess-ttl"
    fake.kv[key]["ts"] = int(time.time()) - (mod._AWAITING_TTL + 10)
    got = await mod.get_awaiting_faces("sess-ttl")
    assert got is None  # scaduto → None, e rimosso
    assert key not in fake.kv


def test_awaiting_ttl_is_30min(fms):
    mod, _ = fms
    # Regressione: era 600 (10min), troppo corto → nomi persi
    assert mod._AWAITING_TTL >= 1800


# ── handle_text_identification: MISS senza awaiting (no save) ────────────────

@pytest.mark.asyncio
async def test_text_id_miss_when_no_awaiting(fms):
    mod, _ = fms
    res = await mod.handle_text_identification("nope", "da sinistra Rita, Zoe")
    assert res["was_awaiting"] is False
    assert res["faces_saved"] is False
    assert res["sistema_msg"] == ""


# ── remaining/all_done: fallback corretto al primo testo senza nomi ──────────

@pytest.mark.asyncio
async def test_remaining_fallback_not_zero(fms, monkeypatch):
    """awaiting senza chiave 'remaining' + faces_saved=False NON deve dare all_done=True."""
    mod, _ = fms
    await mod.set_awaiting_faces("s-rem", "/tmp/x.jpg", "[TOTAL_HUMANS:5]", unknown_count=5)

    async def _no_extract(*a, **k):
        return False, []
    monkeypatch.setattr(mod, "try_extract_faces_from_text", _no_extract)

    res = await mod.handle_text_identification("s-rem", "Chi sono in foto?")
    assert res["was_awaiting"] is True
    assert res["faces_saved"] is False
    # remaining deve riflettere unknown_count, NON il default 0
    assert res["remaining"] == 5
    assert res["all_done"] is False


# ── #B: re-ask iniettato quando l'utente CHIEDE chi sono ─────────────────────

@pytest.mark.asyncio
async def test_reask_injected_on_identity_question(fms, monkeypatch):
    mod, _ = fms
    await mod.set_awaiting_faces("s-reask", "/tmp/x.jpg", "[TOTAL_HUMANS:4]", unknown_count=4)

    async def _no_extract(*a, **k):
        return False, []
    monkeypatch.setattr(mod, "try_extract_faces_from_text", _no_extract)

    res = await mod.handle_text_identification("s-reask", "Conosci chi sono i soggetti in foto?")
    assert res["faces_saved"] is False
    assert "[SISTEMA:" in res["sistema_msg"]
    # deve istruire a NON negare di vedere l'immagine
    assert "non vedi" in res["sistema_msg"].lower()


@pytest.mark.asyncio
async def test_no_reask_on_unrelated_text(fms, monkeypatch):
    mod, _ = fms
    await mod.set_awaiting_faces("s-unrel", "/tmp/x.jpg", "[TOTAL_HUMANS:4]", unknown_count=4)

    async def _no_extract(*a, **k):
        return False, []
    monkeypatch.setattr(mod, "try_extract_faces_from_text", _no_extract)

    res = await mod.handle_text_identification("s-unrel", "Che tempo fa a Roma?")
    assert res["faces_saved"] is False
    assert res["sistema_msg"] == ""  # nessun re-ask su testo non correlato


# ── #3: speaker_name propagato a try_extract (auto-riferimento) ──────────────

@pytest.mark.asyncio
async def test_speaker_name_propagated(fms, monkeypatch):
    mod, _ = fms
    await mod.set_awaiting_faces("s-self", "/tmp/x.jpg", "[TOTAL_HUMANS:1]", unknown_count=1)

    captured = {}

    async def _spy_extract(text, tmp_img, desc_img, session_uid, speaker_name=None):
        captured["speaker_name"] = speaker_name
        return False, []
    monkeypatch.setattr(mod, "try_extract_faces_from_text", _spy_extract)

    await mod.handle_text_identification("s-self", "sono io", speaker_name="Alfio")
    assert captured.get("speaker_name") == "Alfio"
