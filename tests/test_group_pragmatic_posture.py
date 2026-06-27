from core.group_pragmatics import (
    POSTURE_ASSISTANT_OBSERVER,
    POSTURE_DIRECT_ASSISTANT,
    POSTURE_DRAFT_HELPER,
    POSTURE_NEUTRAL_SUPPORT,
    POSTURE_SILENT,
    classify_group_message_role,
    enforce_group_pragmatic_response,
    group_pragmatic_prompt,
    sanitize_group_observer_response,
)


def test_whatsapp_social_observer_does_not_reply_as_recipient():
    role = classify_group_message_role("Tantissimi auguri Maria ❤️")

    assert role.social_event is True
    assert role.addressed_to_human is True
    assert role.recommended_response_posture == POSTURE_ASSISTANT_OBSERVER

    cleaned, changed = sanitize_group_observer_response("Grazie per gli auguri!", role)
    assert changed is True
    assert "grazie per gli auguri" not in cleaned.lower()


def test_telegram_social_uses_same_observer_policy():
    role = classify_group_message_role("Tantissimi auguri Maria ❤️")
    prompt = group_pragmatic_prompt(role, "Ada")

    assert role.recommended_response_posture == POSTURE_ASSISTANT_OBSERVER
    assert "assistant_observer" in prompt
    assert "non dire 'grazie'" in prompt.lower()


def test_whatsapp_celebration_does_not_reply_as_protagonist():
    role = classify_group_message_role("Bravissima, finalmente libera, ce l’hai fatta!")

    assert role.social_event is True
    assert role.recommended_response_posture == POSTURE_ASSISTANT_OBSERVER

    cleaned, changed = sanitize_group_observer_response("Sono felicissima, grazie!", role)
    assert changed is True
    assert "sono felicissima" not in cleaned.lower()
    assert role.addressed_to_human is True


def test_delicate_message_is_neutral_support_not_recipient():
    role = classify_group_message_role("Mi dispiace tanto per questa perdita, ti siamo vicini.")

    assert role.delicate_event is True
    assert role.insufficient_context is True
    assert role.recommended_response_posture == POSTURE_NEUTRAL_SUPPORT

    cleaned, changed = sanitize_group_observer_response(
        "Grazie, Ada. Il tuo sostegno significa molto in questo momento difficile.",
        role,
    )
    assert changed is True
    assert "il tuo sostegno significa molto" not in cleaned.lower()
    assert "non conosco bene il contesto" in cleaned.lower()


def test_telegram_delicate_uses_same_neutral_support_policy():
    role = classify_group_message_role("Mi dispiace tanto per questa perdita, ti siamo vicini.")
    prompt = group_pragmatic_prompt(role, "Ada")

    assert role.recommended_response_posture == POSTURE_NEUTRAL_SUPPORT
    assert "neutral_support" in prompt
    assert "non dire grazie per il sostegno" in prompt.lower()


def test_draft_helper_for_reply_request():
    role = classify_group_message_role(
        "Genesi, rispondi in modo naturale a questa frase: mi dispiace per questa perdita."
    )
    prompt = group_pragmatic_prompt(role, "Ada")

    assert role.directed_to_genesi is True
    assert role.asks_genesi_to_draft_reply is True
    assert role.recommended_response_posture == POSTURE_DRAFT_HELPER
    assert "bozza" in prompt.lower()
    assert "non rispondere come se la frase citata fosse rivolta a te" in prompt.lower()


def test_telegram_draft_helper_fallback_rewrites_direct_output():
    role = classify_group_message_role(
        "Genesi, rispondi in modo naturale a questa frase: mi dispiace per questa perdita."
    )

    cleaned, changed, reason = enforce_group_pragmatic_response(
        "Mi dispiace per questa perdita. È sempre difficile affrontare momenti del genere.",
        role,
    )

    assert changed is True
    assert reason == "non_compliant_output"
    assert cleaned.startswith("Puoi rispondere così:")
    assert "Mi dispiace per questa perdita" not in cleaned


def test_whatsapp_draft_helper_accepts_compliant_draft():
    role = classify_group_message_role(
        "Genesi, rispondi in modo naturale a questa frase: mi dispiace per questa perdita."
    )
    draft = "Puoi rispondere così: «Ti sono vicino/a in questo momento difficile.»"

    cleaned, changed, reason = enforce_group_pragmatic_response(draft, role)

    assert cleaned == draft
    assert changed is False
    assert reason == ""


def test_direct_assistant_for_direct_question():
    role = classify_group_message_role("Genesi, cosa ne pensi?")

    assert role.directed_to_genesi is True
    assert role.recommended_response_posture == POSTURE_DIRECT_ASSISTANT


def test_pronouns_alone_are_not_directed_to_genesi():
    for text in ("ti siamo vicini", "ti vogliamo bene", "sono contento per te"):
        role = classify_group_message_role(text)
        assert role.directed_to_genesi is False
        assert role.recommended_response_posture == POSTURE_SILENT


def test_emoji_only_stays_silent():
    role = classify_group_message_role("❤️❤️❤️🥳🥳🥳")

    assert role.recommended_response_posture == POSTURE_SILENT
    assert role.reason == "emoji_only"


def test_prompt_leak_filtered_then_impersonation_filtered():
    role = classify_group_message_role("Mi dispiace tanto per questa perdita, ti siamo vicini.")
    cleaned, changed = sanitize_group_observer_response(
        "Grazie per il sostegno, la tua vicinanza mi aiuta.",
        role,
    )

    assert changed is True
    assert "grazie per il sostegno" not in cleaned.lower()
    assert "la tua vicinanza mi aiuta" not in cleaned.lower()


def test_observer_impersonation_still_uses_shared_enforcement():
    role = classify_group_message_role("Mi dispiace tanto per questa perdita, ti siamo vicini.")

    cleaned, changed, reason = enforce_group_pragmatic_response(
        "Grazie per il sostegno, la tua vicinanza mi aiuta.",
        role,
    )

    assert changed is True
    assert reason == "impersonation_output"
    assert "grazie per il sostegno" not in cleaned.lower()
