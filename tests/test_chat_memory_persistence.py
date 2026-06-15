"""
tests/test_chat_memory_persistence.py

P1 — il filo della conversazione deve sopravvivere ai restart.
chat_memory ha cache RAM (memory_storage) + mirror su disco. Un restart svuota
la RAM ma il disco ricostruisce. Qui simuliamo il restart svuotando la cache.
"""
import importlib
import pytest


@pytest.fixture
def chat_mem(tmp_path, monkeypatch):
    """chat_memory con buffer su disco isolato in tmp_path."""
    import core.chat_memory as cm
    importlib.reload(cm)
    monkeypatch.setattr(cm, "_CHAT_BUFFER_DIR", str(tmp_path / "chat_buffer"))
    # cache RAM pulita
    cm.memory_storage.clear()
    return cm


def test_survives_restart(chat_mem):
    cm = chat_mem
    uid = "user@test"
    cm.chat_memory.add_message(uid, "ciao", "ciao a te", "greeting")
    cm.chat_memory.add_message(uid, "come stai?", "bene!", "how_are_you")
    assert cm.chat_memory.get_message_count(uid) == 2

    # Simula RESTART: la cache RAM si azzera, il disco resta
    cm.memory_storage.clear()

    msgs = cm.chat_memory.get_messages(uid)
    assert len(msgs) == 2  # ripristinati dal disco
    assert msgs[0]["user_message"] == "ciao"
    assert msgs[1]["system_response"] == "bene!"


def test_add_after_restart_keeps_thread(chat_mem):
    cm = chat_mem
    uid = "user2@test"
    cm.chat_memory.add_message(uid, "m1", "r1", "chat")
    cm.memory_storage.clear()  # restart
    # un nuovo messaggio NON deve perdere quelli precedenti
    cm.chat_memory.add_message(uid, "m2", "r2", "chat")
    msgs = cm.chat_memory.get_messages(uid)
    assert [m["user_message"] for m in msgs] == ["m1", "m2"]


def test_clear_removes_disk(chat_mem):
    cm = chat_mem
    uid = "user3@test"
    cm.chat_memory.add_message(uid, "x", "y", "chat")
    cm.chat_memory.clear_messages(uid)
    cm.memory_storage.clear()  # restart
    assert cm.chat_memory.get_messages(uid) == []  # niente da ripristinare


def test_user_id_with_special_chars(chat_mem):
    """user_id con @ / : non deve rompere il path su disco."""
    cm = chat_mem
    uid = "telegram:-100/abc@x"
    cm.chat_memory.add_message(uid, "hi", "ho", "chat")
    cm.memory_storage.clear()
    assert cm.chat_memory.get_message_count(uid) == 1
