"""Tests for game/chatlog.py. Usage: python3 tools/test_chatlog.py"""
import os
import sys
import tempfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game"))
import chatlog  # noqa: E402

HISTORY = [
    {"role": "assistant", "content": "Hello!", "swipes": ["Hi.", "Hello!"], "swipe_id": 1,
     "mood": "joy", "moods": ["neutral", "joy"]},
    {"role": "user", "content": "How are you?"},
    {"role": "assistant", "content": "*She smiles.* Good.", "swipes": ["*She smiles.* Good."], "swipe_id": 0,
     "mood": "joy", "moods": ["joy"]},
    {"role": "user", "content": "Ünïcode ✓ and {braces} [brackets]"},
    {"role": "assistant", "content": "Nice.", "swipes": ["Nice."], "swipe_id": 0,
     "mood": "neutral", "moods": ["neutral"]},
]


def test_round_trip():
    d = tempfile.mkdtemp()
    path = chatlog.new_chat_path(os.path.join(d, "chats", "Mira"), "Mira")
    chatlog.write_chat(path, HISTORY, "Sam", "Mira")
    meta, hist = chatlog.read_chat(path)
    assert meta["user_name"] == "Sam" and meta["character_name"] == "Mira"
    assert all(m.get("send_date") for m in hist)
    assert [{k: v for k, v in m.items() if k != "send_date"} for m in hist] == HISTORY, hist
    # Dates survive a second round trip unchanged.
    chatlog.write_chat(path, hist, "Sam", "Mira")
    assert chatlog.read_chat(path)[1] == hist
    assert chatlog.list_chats(os.path.dirname(path)) == [path]


def test_sillytavern_fixture():
    meta, hist = chatlog.read_chat(os.path.join(ROOT, "tools", "fixtures", "st_chat.jsonl"))
    assert meta["character_name"] == "Mira"
    assert [m["role"] for m in hist] == ["assistant", "user", "assistant"], hist   # system msg skipped
    assert hist[0]["swipes"][1].startswith("*The tavern is empty") and hist[0]["swipe_id"] == 0
    assert hist[2]["content"] == "Coming right up! *She slides a mug over.*" and hist[2]["swipe_id"] == 1
    assert hist[1]["content"] == "Hi Mira! An ale, please."
    assert hist[1]["send_date"] == "May 1, 2024 6:31pm"


def test_atomic_write():
    d = tempfile.mkdtemp()
    path = os.path.join(d, "c.jsonl")
    chatlog.write_chat(path, HISTORY, "Sam", "Mira")
    before = open(path, "rb").read()
    calls = {"n": 0}
    real = chatlog.json.dumps

    def boom(*a, **k):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated crash mid-write")
        return real(*a, **k)

    with mock.patch.object(chatlog.json, "dumps", boom):
        try:
            chatlog.write_chat(path, HISTORY + [{"role": "user", "content": "more"}], "Sam", "Mira")
        except RuntimeError:
            pass
    assert open(path, "rb").read() == before, "main file must be untouched after a failed write"


def test_bad_types_are_skipped():
    lines = [["not", "a", "dict"], {"mes": 5}, {"mes": "ok", "is_user": True},
             {"mes": "hi", "extra": "x", "swipes": "nope", "swipe_id": "a"}]
    meta, hist = chatlog.from_lines(lines)
    assert [m["content"] for m in hist] == ["ok", "hi"], hist


def test_st_folders_reject_traversal():
    d = tempfile.mkdtemp()
    chars = os.path.join(d, "data", "u", "characters")
    os.makedirs(chars)
    os.makedirs(os.path.join(d, "secret"))
    card = {"name": "../../../secret", "path": os.path.join(chars, "x.png")}
    assert chatlog.sillytavern_chat_folders(card, [chars]) == []


def test_st_folders():
    d = tempfile.mkdtemp()
    chars = os.path.join(d, "data", "default-user", "characters")
    os.makedirs(chars)
    os.makedirs(os.path.join(d, "data", "default-user", "chats", "Mira"))
    card = {"name": "Mira", "path": os.path.join(chars, "Mira.png")}
    assert chatlog.sillytavern_chat_folders(card, [chars]) == [os.path.join(d, "data", "default-user", "chats", "Mira")]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all chatlog tests passed")
