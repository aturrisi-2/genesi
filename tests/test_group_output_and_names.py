import inspect

from core.name_utils import extract_first_name_from_display_name
from core.response_filter import strip_leading_speaker_prefix


def test_strip_bot_speaker_prefixes():
    assert strip_leading_speaker_prefix("Genesi: Va bene, procedo.") == "Va bene, procedo."
    assert strip_leading_speaker_prefix("Assistente: certo.") == "certo."
    assert strip_leading_speaker_prefix("Assistant: Va bene") == "Va bene"


def test_strip_generated_name_prefix_without_breaking_reported_speech():
    assert strip_leading_speaker_prefix("Luca: Va bene") == "Va bene"
    assert strip_leading_speaker_prefix("Luca: ti rispondo cosi.") == "ti rispondo cosi."
    assert strip_leading_speaker_prefix("Ore 8: ci vediamo") == "Ore 8: ci vediamo"
    assert strip_leading_speaker_prefix("Marco: ha detto che arriva") == "Marco: ha detto che arriva"


def test_extract_first_name_from_common_display_names():
    assert extract_first_name_from_display_name("Mario Rossi")["first_name"] == "Mario"
    assert extract_first_name_from_display_name("Mario Rossi")["confidence"] >= 0.9
    assert extract_first_name_from_display_name("Rossi Mario")["first_name"] == "Mario"
    assert extract_first_name_from_display_name("Rossi Mario")["confidence"] >= 0.8
    assert extract_first_name_from_display_name("Turrisi Alfio")["first_name"] == "Alfio"
    assert extract_first_name_from_display_name("Alfio T.")["first_name"] == "Alfio"


def test_extract_first_name_from_dirty_display_names():
    assert extract_first_name_from_display_name("🔥 Marco TAB")["first_name"] == "Marco"
    assert extract_first_name_from_display_name("Mimmo Elettricista")["first_name"] == "Mimmo"
    assert extract_first_name_from_display_name("Zio Pino")["first_name"] == "Pino"


def test_extract_first_name_refuses_low_confidence_or_non_names():
    ing = extract_first_name_from_display_name("Ing. Bianchi")
    assert ing["first_name"] in (None, "Bianchi")
    assert ing["confidence"] < 0.65
    assert extract_first_name_from_display_name("+39 333 1234567")["first_name"] is None
    assert extract_first_name_from_display_name("Capo squadra")["first_name"] is None
    assert extract_first_name_from_display_name("SSA_Ufficio")["first_name"] is None


def test_extract_first_name_reduces_full_display_names_to_single_name():
    assert extract_first_name_from_display_name("Dora Cirasa")["first_name"] == "Dora"
    assert extract_first_name_from_display_name("🔥 Dora Cirasa 🍒")["first_name"] == "Dora"
    assert extract_first_name_from_display_name("Marco TAB CEFLA")["first_name"] == "Marco"
    assert extract_first_name_from_display_name("Zio Tony")["first_name"] == "Tony"
    assert extract_first_name_from_display_name("Skipper")["first_name"] == "Skipper"


def test_extract_first_name_keeps_known_composite_first_names():
    mg = extract_first_name_from_display_name("Maria Grazia Rossi")
    assert mg["first_name"] == "Maria Grazia"
    assert mg["confidence"] >= 0.8
    am = extract_first_name_from_display_name("Anna Maria Bianchi")
    assert am["first_name"] == "Anna Maria"
    gb = extract_first_name_from_display_name("Giovan Battista Verdi")
    assert gb["first_name"] == "Giovan Battista"
    # Nome già scritto unito non viene spezzato né alterato
    assert extract_first_name_from_display_name("Gianluca")["first_name"] == "Gianluca"


def test_extract_first_name_handles_surname_first_display_names():
    # 3+ token con cognome iniziale: il nome proprio è il secondo token
    assert extract_first_name_from_display_name("Rossi Pina Bianchi")["first_name"] == "Pina"
    assert extract_first_name_from_display_name("Turrisi Pina Nino Calvagna")["first_name"] == "Pina"
    # Composto in mezzo: intercettato come unico nome
    assert extract_first_name_from_display_name("Rossi Maria Grazia Bianchi")["first_name"] == "Maria Grazia"
    assert extract_first_name_from_display_name("Bianchi Anna Maria Verdi")["first_name"] == "Anna Maria"
    # 2 token resta "Nome Cognome" → primo token
    assert extract_first_name_from_display_name("Dora Cirasa")["first_name"] == "Dora"


def test_non_person_display_name_is_not_confident():
    res = extract_first_name_from_display_name("Gruppo Enel Roma")
    assert res["confidence"] < 0.65


async def test_silent_participant_appears_with_short_name_not_full_display():
    import random
    from core.telegram_group_memory import build_group_context

    chat_id = random.randint(900_000_000, 999_999_999)
    participants = [
        {"id": "10000000001@s.whatsapp.net", "name": "Dora Cirasa", "is_me": False},
    ]
    ctx = await build_group_context(
        chat_id, from_id=chat_id, first_name="Tester",
        current_message="ciao", participants=participants,
    )
    assert "Dora Cirasa" not in ctx
    assert "Dora" in ctx


async def test_silent_participant_surname_first_appears_with_first_name():
    import random
    from core.telegram_group_memory import build_group_context

    chat_id = random.randint(900_000_000, 999_999_999)
    participants = [
        {"id": "10000000002@s.whatsapp.net", "name": "Turrisi Pina Nino Calvagna", "is_me": False},
    ]
    ctx = await build_group_context(
        chat_id, from_id=chat_id, first_name="Tester",
        current_message="ciao", participants=participants,
    )
    assert "Turrisi Pina Nino Calvagna" not in ctx
    assert "Pina" in ctx


def test_group_formatting_helpers_do_not_contain_case_specific_hardcoding():
    forbidden = [
        "Simo" + "na",
        "non" + "na",
        "Whats" + "App",
        "TAB CE" + "FLA",
        "can" + "tiere",
        "Cef" + "la",
    ]
    source = (
        inspect.getsource(extract_first_name_from_display_name)
        + inspect.getsource(strip_leading_speaker_prefix)
    )
    lowered = source.lower()
    assert not any(item.lower() in lowered for item in forbidden)
