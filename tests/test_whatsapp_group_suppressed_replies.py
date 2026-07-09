import inspect

import pytest
import core.whatsapp_bot as wa


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("[Silenzio]", True),
        ("[Silenzio].", True),
        (" [Silenzio] ", True),
        ("Mi dispiace, non posso rispondere a questo messaggio.", True),
        ("Non posso rispondere a questo messaggio.", True),
        ("Mi dispiace, non posso rispondere a questo messaggio", True),
        ("Mi dispiace, NON POSSO RISPONDERE A QUESTO MESSAGGIO", True),
        ("Certo, ecco le informazioni richieste.", False),
        ("Buongiorno a tutti, oggi è una bella giornata!", False),
        ("C'è silenzio nella stanza.", False),
        ("", False),
        (None, False),
    ],
)
def test_should_suppress_group_reply(reply, expected):
    assert wa._should_suppress_group_reply(reply) is expected


def test_group_suppress_guard_is_in_handle_reply_path():
    source = inspect.getsource(wa._process_message)
    assert "if is_group and chat_id and _should_suppress_group_reply(reply):" in source
    assert "WA_GROUP_REPLY_SUPPRESSED" in source
