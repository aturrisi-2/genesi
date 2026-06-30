"""Per-group operational reply control.

Reply is enabled when the global env flag is on OR when the specific group is
whitelisted in Admin group_controls. Enabling one group (canary) must never
enable another (TAB). Synthetic data only; no WhatsApp, no network.
"""
import core.operational_memory.whatsapp_operational as wo
import core.group_controls as gc

CANARY = "120363428502905378@g.us"
TAB = "120363404290146040@g.us"


def test_global_env_off_no_group_reply_off(monkeypatch):
    monkeypatch.setattr(wo, "env_flag", lambda name, default=False: False)
    assert wo.is_whatsapp_operational_reply_enabled() is False
    assert wo.is_whatsapp_operational_reply_enabled(CANARY) is False


def test_global_env_on_enables_all(monkeypatch):
    monkeypatch.setattr(wo, "env_flag", lambda name, default=False: True)
    assert wo.is_whatsapp_operational_reply_enabled() is True
    assert wo.is_whatsapp_operational_reply_enabled(TAB) is True


def test_per_group_canary_only(monkeypatch):
    # global env OFF; only canary whitelisted in Admin controls
    monkeypatch.setattr(wo, "env_flag", lambda name, default=False: False)

    def fake_is_group_reply_enabled(platform, group_id):
        return platform == "whatsapp" and group_id == CANARY

    monkeypatch.setattr(gc, "is_group_reply_enabled", fake_is_group_reply_enabled)
    assert wo.is_whatsapp_operational_reply_enabled(CANARY) is True
    # TAB stays OFF — per-group activation does not leak
    assert wo.is_whatsapp_operational_reply_enabled(TAB) is False
    # no group passed → still OFF
    assert wo.is_whatsapp_operational_reply_enabled() is False


def test_group_controls_error_is_safe(monkeypatch):
    monkeypatch.setattr(wo, "env_flag", lambda name, default=False: False)

    def boom(platform, group_id):
        raise RuntimeError("controls unavailable")

    monkeypatch.setattr(gc, "is_group_reply_enabled", boom)
    # fail-closed: no reply on error
    assert wo.is_whatsapp_operational_reply_enabled(CANARY) is False
