from __future__ import annotations

import pytest

from core.operational_memory.invocation_router import is_invoked
from core.operational_memory.models import InvocationConfig


def test_normal_message_is_silent():
    d = is_invoked("ragazzi domani portiamo il materiale")
    assert d.respond is False and d.mode == "silent"


def test_name_at_start_invokes():
    d = is_invoked("Genesi, fammi il punto")
    assert d.respond is True and d.mode == "name"
    assert d.query == "fammi il punto"


def test_tag_invokes_anywhere():
    d = is_invoked("@genesi cosa resta aperto?")
    assert d.respond is True and d.mode == "tag"
    assert d.query == "cosa resta aperto?"


def test_command_prefix_invokes():
    d = is_invoked("/genesi report")
    assert d.respond is True and d.mode == "command"
    assert d.query == "report"


def test_bare_invocation_defaults_to_briefing():
    d = is_invoked("Genesi?")
    assert d.respond is True
    assert d.query == "fammi il punto"


def test_name_not_at_start_stays_silent():
    # Mention of the name mid-sentence is not an invocation (avoid false positives).
    d = is_invoked("ieri ho visto genesi al cantiere")
    assert d.respond is False


def test_dm_invokes_when_allowed():
    d = is_invoked("cosa è cambiato?", is_dm=True)
    assert d.respond is True and d.mode == "dm"


def test_dm_silent_when_disabled():
    cfg = InvocationConfig(respond_in_dm=False)
    d = is_invoked("cosa è cambiato?", cfg, is_dm=True)
    assert d.respond is False


def test_authorized_trigger():
    cfg = InvocationConfig(authorized_triggers=["report operativo"])
    d = is_invoked("per favore report operativo completo", cfg)
    assert d.respond is True and d.mode == "trigger"


def test_custom_bot_name():
    cfg = InvocationConfig(bot_names=["aria"])
    assert is_invoked("Aria, fammi il report", cfg).respond is True
    assert is_invoked("Genesi, fammi il report", cfg).respond is False


def test_empty_message_silent():
    assert is_invoked("   ").respond is False


def test_no_hardcoded_domain_tokens():
    import re

    import core.operational_memory.invocation_router as mod

    body = open(mod.__file__, "r", encoding="utf-8").read().upper()
    for token in ["TAB CEFLA", "T6", "T7", "UTA", "EWC05", "SS01", "B02", "CANTIERE", "WHATSAPP"]:
        assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded token: {token}"
