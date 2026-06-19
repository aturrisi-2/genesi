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
