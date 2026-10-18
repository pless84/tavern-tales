"""Tests for game/stcards.py. Usage: python3 tools/test_cards.py"""
import base64
import json
import os
import struct
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game"))
import stcards  # noqa: E402


def png_with(chunks):
    def chunk(t, body):
        return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body) & 0xFFFFFFFF)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    for t, body in chunks:
        out += chunk(t, body)
    return out + chunk(b"IDAT", zlib.compress(b"\0\0\0\0\0")) + chunk(b"IEND", b"")


def b64(obj):
    return base64.b64encode(json.dumps(obj).encode()).decode()


def main():
    d = tempfile.mkdtemp()
    v3 = {"spec": "chara_card_v3", "data": {"name": "Vee", "first_mes": "Hi {{user}}, I'm {{char}}.", "description": "ünïcode"}}
    v2 = {"spec": "chara_card_v2", "data": {"name": "Old", "first_mes": "x"}}
    # V3 should win over the legacy chara chunk.
    open(os.path.join(d, "a.png"), "wb").write(png_with([(b"tEXt", b"chara\0" + b64(v2).encode()), (b"tEXt", b"ccv3\0" + b64(v3).encode())]))
    # iTXt compressed chunk.
    itxt = b"chara\0\x01\x00\0\0" + zlib.compress(b64({"name": "Zed", "char_greeting": "yo"}).encode())
    open(os.path.join(d, "b.png"), "wb").write(png_with([(b"iTXt", itxt)]))
    # Plain PNG without data -> error, not crash.
    open(os.path.join(d, "c.png"), "wb").write(png_with([]))
    # JSON + same-named avatar PNG.
    json.dump({"char_name": "Jay", "char_persona": "calm"}, open(os.path.join(d, "j.json"), "w"))
    open(os.path.join(d, "j.png"), "wb").write(png_with([]))

    cards, errors = stcards.scan([d])
    by = {c["name"]: c for c in cards}
    assert set(by) == {"Vee", "Zed", "Jay"}, by.keys()
    assert by["Vee"]["description"] == "ünïcode"
    assert by["Zed"]["first_mes"] == "yo"
    assert by["Jay"]["personality"] == "calm" and by["Jay"]["avatar"].endswith("j.png")
    assert len(errors) == 1 and errors[0][0].endswith("c.png"), errors
    assert stcards.apply_macros(by["Vee"]["first_mes"], "Vee", "Sam") == "Hi Sam, I'm Vee."
    assert stcards.apply_macros("<USER> & <BOT>", "B", "U") == "U & B"
    assert stcards.apply_macros("{{user}} is {{Persona}}", "B", "Sam", "a bard") == "Sam is a bard"

    # Generated sample cards load too.
    cards, errors = stcards.scan([os.path.join(ROOT, "characters")])
    names = sorted(c["name"] for c in cards)
    assert {"Mira", "Rook"} <= set(names) and not errors, (names, errors)
    mira = [c for c in cards if c["name"] == "Mira"][0]
    assert mira["lorebook"] and mira["alternate_greetings"]
    # Expression sprite discovery.
    sd = tempfile.mkdtemp()
    os.makedirs(os.path.join(sd, "Vee"))
    for f in ("joy.png", "neutral.webp", "banana.png", "notes.txt", "Surprise.PNG"):
        open(os.path.join(sd, "Vee", f), "wb").write(b"x")
    ex = stcards.find_expressions({"name": "Vee", "path": os.path.join(sd, "vee_card.png")}, [sd])
    assert set(ex) == {"joy", "neutral", "surprise"}, ex
    assert stcards.find_expressions({"name": "Nobody"}, [sd]) == {}
    # Folder named after the card file also works.
    os.makedirs(os.path.join(sd, "vee_card"))
    open(os.path.join(sd, "vee_card", "anger.png"), "wb").write(b"x")
    ex2 = stcards.find_expressions({"name": "Other", "path": os.path.join(sd, "vee_card.png")}, [sd])
    assert set(ex2) == {"anger"}, ex2
    assert set(stcards.find_expressions(mira, [os.path.join(ROOT, "characters")])) >= {"neutral", "joy", "surprise"}
    # Security: regex-special names, traversal names, compressed-chunk bombs.
    assert stcards.apply_macros("Hi {{char}}", "a\\1b\\g<0>", "U") == "Hi a\\1b\\g<0>"
    assert not stcards.safe_folder_name("../x") and not stcards.safe_folder_name("/etc") and stcards.safe_folder_name("Mira")
    assert stcards.find_expressions({"name": "../" + os.path.basename(sd) + "/Vee"}, [os.path.join(sd, "Vee")]) == {}
    bomb = zlib.compress(b"A" * (stcards.MAX_TEXT_BYTES + 10))
    open(os.path.join(d, "bomb.png"), "wb").write(png_with([(b"zTXt", b"chara\0\0" + bomb)]))
    try:
        stcards.load_card(os.path.join(d, "bomb.png"))
        raise AssertionError("bomb should be refused")
    except stcards.CardError:
        pass
    # A used-up budget must refuse, not inflate unlimited (zlib max_length=0 means no limit).
    budget = [5]
    assert stcards._inflate(zlib.compress(b"12345"), budget) == b"12345" and budget[0] == 0
    for buf in (zlib.compress(b"A" * 1000), zlib.compress(b"")):
        try:
            stcards._inflate(buf, budget)
            raise AssertionError("exhausted budget should refuse")
        except stcards.CardError:
            pass
    # Boundary: output that exactly fits is fine, one byte over is refused.
    assert stcards._inflate(zlib.compress(b"A" * 100), [100]) == b"A" * 100
    try:
        stcards._inflate(zlib.compress(b"A" * 100), [99])
        raise AssertionError("over-limit stream should refuse")
    except stcards.CardError:
        pass
    # Unwanted compressed chunks are never inflated.
    open(os.path.join(d, "other.png"), "wb").write(png_with([(b"zTXt", b"comment\0\0" + bomb), (b"tEXt", b"chara\0" + b64(v2).encode())]))
    assert stcards.load_card(os.path.join(d, "other.png"))["name"] == "Old"
    # Wrong JSON types don't crash.
    weird = stcards.normalize({"char_name": 5, "data": {"name": "W", "alternate_greetings": "x", "tags": 3,
                                                         "character_book": {"entries": [{"keys": "k", "content": 7}]}}})
    assert weird["name"] == "W" and weird["alternate_greetings"] == [] and weird["lorebook"][0]["content"] == ""
    print("all card tests passed")


if __name__ == "__main__":
    main()
