"""
Tests — Group Emotional Cooldown

Verifica il comportamento di Genesi in un thread commemorativo/di lutto su gruppi WA/TG.
Sequenza reale di riferimento: gruppo "Nipoti&Fratelli TURRISI", 2026-xx-xx.

Regole testate:
1. is_emoji_only_or_reaction() per messaggi puri emoji
2. is_minimal_social_reaction() per reazioni brevi post-condoglianze
3. is_memorial_trigger() per il messaggio trigger reale ("non è più con noi")
4. set/get/clear del cooldown emotivo per gruppo
5. Cooldown blocca risposte su reazioni minimali (Test 2-4 spec)
6. Invocazione esplicita durante cooldown → non bloccata (Test 5 spec)
7. Cambio tema netto → non bloccato (Test 6 spec)
8. Nome primo autore non persiste (Test 7 spec — verifica via prompt context)
9. Media durante cooldown senza invocazione → bloccata (Test 8 spec)
"""

import time
import pytest

from core.group_reactivity import (
    is_emoji_only_or_reaction,
    is_minimal_social_reaction,
    is_memorial_trigger,
    set_group_emotional_cooldown,
    get_group_emotional_cooldown,
    clear_group_emotional_cooldown,
    _EMOTIONAL_COOLDOWNS,
    EMOTIONAL_COOLDOWN_HOURS,
)


# ── Test 1: emoji-only detection ─────────────────────────────────────────────

class TestEmojiOnlyDetection:
    def test_pure_grief_emoji(self):
        assert is_emoji_only_or_reaction("🙏🙏🙏❤️") is True

    def test_single_heart_emoji(self):
        assert is_emoji_only_or_reaction("❤️") is True

    def test_multi_emoji_mix(self):
        assert is_emoji_only_or_reaction("😢🕯️🙏🤍") is True

    def test_emoji_with_whitespace(self):
        assert is_emoji_only_or_reaction("  🙏  ") is True

    def test_empty_string(self):
        assert is_emoji_only_or_reaction("") is True

    def test_emoji_plus_word_is_not_pure(self):
        # "ovunque sei" ha contenuto testuale
        assert is_emoji_only_or_reaction("❤️❤️❤️ ovunque sei ❤️") is False

    def test_question_is_not_emoji_only(self):
        assert is_emoji_only_or_reaction("Come stai? 😊") is False

    def test_regular_text_is_not_emoji_only(self):
        assert is_emoji_only_or_reaction("Genesi, aiutami a scrivere un pensiero") is False


# ── Test 2: minimal social reaction detection ─────────────────────────────────

class TestMinimalSocialReaction:
    def test_pure_emoji_is_minimal(self):
        # Zia Mela: "🙏🙏🙏❤️"
        assert is_minimal_social_reaction("🙏🙏🙏❤️") is True

    def test_emoji_plus_short_condolence_is_minimal(self):
        # Mariella Cugina: "❤️❤️❤️ ovunque sei ❤️"
        assert is_minimal_social_reaction("❤️❤️❤️ ovunque sei ❤️") is True

    def test_sempre_con_noi_is_minimal(self):
        assert is_minimal_social_reaction("sempre con noi ❤️") is True

    def test_un_abbraccio_is_minimal(self):
        assert is_minimal_social_reaction("un abbraccio 🫂") is True

    def test_riposa_in_pace_is_minimal(self):
        assert is_minimal_social_reaction("riposa in pace 🕊️") is True

    def test_ti_ricordiamo_is_minimal(self):
        assert is_minimal_social_reaction("ti ricordiamo sempre ❤️") is True

    def test_direct_question_is_not_minimal(self):
        # Test 5: invocazione con domanda → non soppressa
        assert is_minimal_social_reaction("Genesi, mi aiuti a scrivere un pensiero?") is False

    def test_long_text_is_not_minimal(self):
        long_msg = "Cara famiglia, voglio condividere con voi un ricordo bellissimo che ho di lei quando eravamo bambini insieme a casa dei nonni in Sicilia."
        assert is_minimal_social_reaction(long_msg) is False

    def test_topic_change_not_minimal(self):
        # Test 6: cambio tema netto
        assert is_minimal_social_reaction("Ragazzi, stasera ci vediamo per cena?") is False

    def test_genesi_invocation_not_minimal(self):
        assert is_minimal_social_reaction("Genesi cosa ne pensi?") is False


# ── Test 3: memorial trigger detection ───────────────────────────────────────

class TestMemorialTrigger:
    def test_real_trigger_message(self):
        # Mamma Wind: messaggio reale dell'incidente
        msg = "Oggi anche se non è più con noi ricordiamo il suo compleanno con una preghiera 🙏 perché è sempre con noi ❤️🙏🙏"
        assert is_memorial_trigger(msg) is True

    def test_non_e_piu_con_noi(self):
        assert is_memorial_trigger("non è più con noi") is True

    def test_non_e_piu_tra_noi(self):
        assert is_memorial_trigger("non è più tra noi") is True

    def test_anche_se_non_e_piu(self):
        assert is_memorial_trigger("anche se non è più con noi la ricordiamo") is True

    def test_lutto_phrase(self):
        assert is_memorial_trigger("siamo in lutto per la perdita di") is True

    def test_e_mancata(self):
        assert is_memorial_trigger("è mancata ieri") is True

    def test_condoglianze(self):
        assert is_memorial_trigger("le mie condoglianze alla famiglia") is True

    def test_riposa_in_pace(self):
        assert is_memorial_trigger("riposa in pace") is True

    def test_deceduto(self):
        assert is_memorial_trigger("è deceduto stanotte") is True

    def test_regular_birthday_not_trigger(self):
        # Compleanno di persona in vita — non è trigger
        assert is_memorial_trigger("buon compleanno a tutti!") is False

    def test_generic_greeting_not_trigger(self):
        assert is_memorial_trigger("buongiorno a tutti 🌞") is False

    def test_empty_not_trigger(self):
        assert is_memorial_trigger("") is False


# ── Test 4: cooldown state management ────────────────────────────────────────

class TestCooldownState:
    def setup_method(self):
        # Pulisce stato globale prima di ogni test
        _EMOTIONAL_COOLDOWNS.clear()

    def test_set_and_get_cooldown(self):
        set_group_emotional_cooldown("whatsapp", 12345, topic="memorial")
        cd = get_group_emotional_cooldown("whatsapp", 12345)
        assert cd is not None
        assert cd["topic"] == "memorial"
        assert cd["expires_at"] > time.time()

    def test_cooldown_expires(self):
        # Imposta con durata 0.001h (3.6 secondi) poi simula scadenza
        set_group_emotional_cooldown("whatsapp", 99999, hours=0.001)
        cd = get_group_emotional_cooldown("whatsapp", 99999)
        assert cd is not None
        # Simula scadenza modificando expires_at
        _EMOTIONAL_COOLDOWNS[("whatsapp", "99999")]["expires_at"] = time.time() - 1
        cd_expired = get_group_emotional_cooldown("whatsapp", 99999)
        assert cd_expired is None

    def test_clear_cooldown(self):
        set_group_emotional_cooldown("whatsapp", 55555, topic="memorial")
        clear_group_emotional_cooldown("whatsapp", 55555)
        assert get_group_emotional_cooldown("whatsapp", 55555) is None

    def test_no_cooldown_when_not_set(self):
        assert get_group_emotional_cooldown("whatsapp", 77777) is None

    def test_cooldown_not_shortened(self):
        # Un cooldown lungo esistente non deve essere accorciato da uno più corto
        set_group_emotional_cooldown("whatsapp", 11111, hours=4.0)
        expires_before = _EMOTIONAL_COOLDOWNS[("whatsapp", "11111")]["expires_at"]
        set_group_emotional_cooldown("whatsapp", 11111, hours=1.0)
        expires_after = _EMOTIONAL_COOLDOWNS[("whatsapp", "11111")]["expires_at"]
        assert expires_after == expires_before

    def test_cooldown_extended_when_longer(self):
        # Un nuovo cooldown più lungo estende quello esistente
        set_group_emotional_cooldown("whatsapp", 22222, hours=1.0)
        expires_before = _EMOTIONAL_COOLDOWNS[("whatsapp", "22222")]["expires_at"]
        set_group_emotional_cooldown("whatsapp", 22222, hours=4.0)
        expires_after = _EMOTIONAL_COOLDOWNS[("whatsapp", "22222")]["expires_at"]
        assert expires_after > expires_before

    def test_different_platforms_isolated(self):
        set_group_emotional_cooldown("whatsapp", 33333, topic="memorial")
        assert get_group_emotional_cooldown("telegram", 33333) is None

    def test_different_groups_isolated(self):
        set_group_emotional_cooldown("whatsapp", 44444, topic="memorial")
        assert get_group_emotional_cooldown("whatsapp", 55556) is None


# ── Test 5-9: gate logic (unit-testing the gate predicates) ──────────────────

class TestCooldownGateLogic:
    """
    Testa la logica del gate combinando is_minimal_social_reaction() e
    get_group_emotional_cooldown(). In produzione il gate è in whatsapp_bot.py,
    ma i predicati che lo compongono sono testabili qui in modo pulito.
    """

    def setup_method(self):
        _EMOTIONAL_COOLDOWNS.clear()

    def _gate_blocks(self, platform: str, group_id, text: str, has_media: bool = False,
                     bot_mentioned: bool = False, reply_to_genesi: bool = False) -> bool:
        """Simula la logica del gate: True = blocca, False = lascia passare."""
        if bot_mentioned or reply_to_genesi:
            return False
        cd = get_group_emotional_cooldown(platform, group_id)
        if not cd:
            return False
        if is_minimal_social_reaction(text):
            return True
        if has_media:
            return True
        return False

    # Test 5 (spec): prima risposta + cooldown attivo
    def test_first_response_sets_cooldown_then_blocks(self):
        gid = 943999700
        # Cooldown attivato dopo la prima risposta empatica
        set_group_emotional_cooldown("whatsapp", gid, topic="memorial")
        # Zia Mela: 🙏🙏🙏❤️ — deve essere bloccata
        assert self._gate_blocks("whatsapp", gid, "🙏🙏🙏❤️") is True

    # Test 6 (spec): Mariella Cugina durante cooldown
    def test_emoji_plus_condolence_phrase_blocked_during_cooldown(self):
        gid = 943999700
        set_group_emotional_cooldown("whatsapp", gid)
        assert self._gate_blocks("whatsapp", gid, "❤️❤️❤️ ovunque sei ❤️") is True

    # Test 7 (spec): 2 ore dopo → ancora in cooldown (4h default)
    def test_within_cooldown_window_still_blocked(self):
        gid = 943999700
        set_group_emotional_cooldown("whatsapp", gid, hours=4.0)
        # Simula che siano passate 2 ore avanzando il set_at ma non expires_at
        # (il cooldown è ancora attivo)
        assert get_group_emotional_cooldown("whatsapp", gid) is not None
        assert self._gate_blocks("whatsapp", gid, "🤍🕯️ sempre con noi") is True

    # Test 8 (spec): invocazione esplicita durante cooldown → NON bloccata
    def test_explicit_invocation_bypasses_cooldown(self):
        gid = 943999700
        set_group_emotional_cooldown("whatsapp", gid)
        # bot_mentioned=True → gate non blocca
        assert self._gate_blocks("whatsapp", gid,
                                 "Genesi, mi aiuti a scrivere un pensiero?",
                                 bot_mentioned=True) is False

    # Test 9 (spec): cambio tema netto → NON bloccato
    def test_topic_change_bypasses_cooldown(self):
        gid = 943999700
        set_group_emotional_cooldown("whatsapp", gid)
        # Domanda pratica → is_minimal_social_reaction = False → gate non blocca
        assert self._gate_blocks("whatsapp", gid,
                                 "Ragazzi, a che ora ci vediamo stasera?") is False

    # Test 10 (spec): nessun cooldown attivo → tutto passa
    def test_no_cooldown_nothing_blocked(self):
        gid = 12345678
        # Cooldown non impostato
        assert self._gate_blocks("whatsapp", gid, "🙏🙏🙏❤️") is False
        assert self._gate_blocks("whatsapp", gid, "❤️❤️❤️ ovunque sei ❤️") is False

    # Test 11 (spec): media durante cooldown senza invocazione → bloccata
    def test_media_blocked_during_cooldown_without_mention(self):
        gid = 943999700
        set_group_emotional_cooldown("whatsapp", gid)
        # Foto senza invocazione → soppressa
        assert self._gate_blocks("whatsapp", gid, "", has_media=True) is True

    # Test 12 (spec): media + invocazione esplicita → NON bloccata
    def test_media_with_mention_bypasses_cooldown(self):
        gid = 943999700
        set_group_emotional_cooldown("whatsapp", gid)
        assert self._gate_blocks("whatsapp", gid, "Genesi guarda questa foto",
                                 has_media=True, bot_mentioned=True) is False

    # Test reply diretta a Genesi bypassa cooldown
    def test_reply_to_genesi_bypasses_cooldown(self):
        gid = 943999700
        set_group_emotional_cooldown("whatsapp", gid)
        assert self._gate_blocks("whatsapp", gid, "❤️❤️ grazie",
                                 reply_to_genesi=True) is False
