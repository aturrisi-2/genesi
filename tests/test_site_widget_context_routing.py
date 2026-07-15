from unittest.mock import AsyncMock, Mock

import pytest

from core import simple_chat


@pytest.mark.asyncio
async def test_widget_page_question_bypasses_personal_location_intent(monkeypatch):
    classify = AsyncMock(side_effect=AssertionError("widget must not call intent classifier"))
    handle = AsyncMock(return_value="Questa pagina parla del Centro Interculturale.")

    monkeypatch.setattr(simple_chat.intent_classifier, "classify_async", classify)
    monkeypatch.setattr(simple_chat.proactor, "handle", handle)
    monkeypatch.setattr(simple_chat.user_manager, "get_user", Mock(return_value=True))
    monkeypatch.setattr(simple_chat.user_manager, "increment_messages", Mock())
    monkeypatch.setattr(simple_chat.chat_memory, "add_message", Mock())

    message = (
        "di cosa parla la pagina in cui mi trovo?\n\n"
        "[CONTESTO PAGINA]\nTitolo: Centro Interculturale\n"
        "Contenuto visibile: corsi di italiano L2 e attività culturali."
    )
    response, intent = await simple_chat.simple_chat_handler(
        "site_widget_user",
        message,
        conversation_id="demo-session",
        platform="widget",
    )

    assert response == "Questa pagina parla del Centro Interculturale."
    assert intent == "chat_free"
    classify.assert_not_awaited()
    handle.assert_awaited_once_with(
        user_id="site_widget_user",
        message=message,
        intent=["chat_free"],
        conversation_id="demo-session",
        platform="widget",
    )


@pytest.mark.asyncio
async def test_non_widget_still_uses_normal_intent_classifier(monkeypatch):
    classify = AsyncMock(return_value=["dove_sono"])
    handle = AsyncMock(return_value="Sei a Bologna.")

    monkeypatch.setattr(simple_chat.intent_classifier, "classify_async", classify)
    monkeypatch.setattr(simple_chat.proactor, "handle", handle)
    monkeypatch.setattr(simple_chat.user_manager, "get_user", Mock(return_value=True))
    monkeypatch.setattr(simple_chat.user_manager, "increment_messages", Mock())
    monkeypatch.setattr(simple_chat.chat_memory, "add_message", Mock())

    _, intent = await simple_chat.simple_chat_handler(
        "web_user", "dove mi trovo?", platform="web"
    )

    assert intent == "dove_sono"
    classify.assert_awaited_once()
