"""
Test suite per GroupContext — nessuna regressione garantita.
Verifica che il contesto di gruppo/piattaforma venga propagato correttamente
e che il comportamento senza contesto rimanga identico a prima.
"""

import pytest
from core.group_context import GroupContext, build_group_prompt_block


class TestGroupContextBlock:

    def test_none_returns_empty_string(self):
        assert build_group_prompt_block(None) == ""

    def test_default_web_returns_empty_string(self):
        assert build_group_prompt_block(GroupContext()) == ""

    def test_web_platform_with_no_group_returns_empty(self):
        ctx = GroupContext(platform="web", group_id="", group_name="")
        assert build_group_prompt_block(ctx) == ""

    def test_telegram_casa_turrisi_tone_familiare(self):
        ctx = GroupContext(platform="telegram", group_id="casa_turrisi", group_name="Casa Turrisi")
        block = build_group_prompt_block(ctx)
        assert "Telegram" in block
        assert "Casa Turrisi" in block
        assert "familiare" in block

    def test_whatsapp_swift_tone_professionale(self):
        ctx = GroupContext(platform="whatsapp", group_id="swift", group_name="Swift Dev")
        block = build_group_prompt_block(ctx)
        assert "Whatsapp" in block
        assert "professionale" in block

    def test_prova_genesi_tone_diretto(self):
        ctx = GroupContext(platform="telegram", group_id="prova_genesi", group_name="Prova Genesi")
        block = build_group_prompt_block(ctx)
        assert "diretto" in block or "naturale" in block

    def test_member_count_included(self):
        ctx = GroupContext(platform="whatsapp", group_id="casa_turrisi", member_count=5)
        block = build_group_prompt_block(ctx)
        assert "5" in block

    def test_group_name_takes_precedence_over_id(self):
        ctx = GroupContext(platform="telegram", group_id="g123", group_name="Mio Gruppo")
        block = build_group_prompt_block(ctx)
        assert "Mio Gruppo" in block
        assert "g123" not in block

    def test_no_tone_for_unknown_group(self):
        ctx = GroupContext(platform="telegram", group_id="xyz_unknown_group", group_name="XYZ Unknown")
        block = build_group_prompt_block(ctx)
        # Should still include platform and group name, but no tone line
        assert "XYZ Unknown" in block
        assert "Tono da usare" not in block

    def test_famiglia_keyword_triggers_familiare(self):
        ctx = GroupContext(platform="whatsapp", group_id="famiglia_mia", group_name="Famiglia Mia")
        block = build_group_prompt_block(ctx)
        assert "familiare" in block

    def test_family_keyword_english_triggers_familiare(self):
        ctx = GroupContext(platform="telegram", group_id="family_chat", group_name="Family Chat")
        block = build_group_prompt_block(ctx)
        assert "familiare" in block


class TestGroupContextIntegration:

    def test_prompt_block_injected_correctly(self):
        """Verifica che il blocco sia ben formato per iniezione nel system prompt."""
        ctx = GroupContext(platform="telegram", group_id="casa_turrisi", group_name="Casa Turrisi", member_count=4)
        block = build_group_prompt_block(ctx)
        lines = block.split("\n")
        assert lines[0] == "CONTESTO GRUPPO:"
        assert any("Piattaforma:" in l for l in lines)
        assert any("Gruppo:" in l for l in lines)
        assert any("Membri presenti:" in l for l in lines)
        assert any("Tono da usare:" in l for l in lines)

    def test_block_no_trailing_newline(self):
        ctx = GroupContext(platform="telegram", group_id="casa_turrisi", group_name="Casa Turrisi")
        block = build_group_prompt_block(ctx)
        assert not block.endswith("\n")
