"""Generate the background and sample character cards (pure Python, no deps).

Usage: python3 tools/make_assets.py
"""
import base64
import json
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def write_png(path, w, h, pixel, text_chunks=()):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw += bytes(pixel(x, y))

    def chunk(t, body):
        return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body) & 0xFFFFFFFF)

    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    for key, val in text_chunks:
        out += chunk(b"tEXt", key.encode("latin-1") + b"\0" + val.encode("latin-1"))
    out += chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(out)


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def bg_pixel(x, y):
    w, h = 1280, 720
    c = mix((44, 26, 52), (16, 11, 26), y / h)
    for lx, ly, col in ((220, 180, (255, 170, 90)), (1060, 160, (255, 140, 110)), (640, 90, (200, 150, 255))):
        d = math.hypot(x - lx, y - ly)
        c = mix(c, col, 0.55 * math.exp(-(d / 210.0) ** 2))
    if y > 560:  # bar counter
        c = mix(c, (60, 34, 30), 0.85)
        if y < 570:
            c = (110, 70, 50)
    return c + (255,)


def make_portrait(hair, skin, cloth, eye, expr="neutral"):
    w, h = 400, 560

    def px(x, y):
        c = mix((60, 40, 80), (25, 18, 40), y / h)
        cx = 200
        # shoulders / body
        if y > 380 and abs(x - cx) < 60 + (y - 380) * 0.9:
            return mix(cloth, (0, 0, 0), (y - 380) / 400) + (255,)
        # neck
        if 300 < y <= 390 and abs(x - cx) < 30:
            return skin + (255,)
        # hair back
        if math.hypot((x - cx) / 120.0, (y - 250) / 170.0) < 1:
            c = hair
        # face
        if math.hypot((x - cx) / 82.0, (y - 225) / 102.0) < 1:
            c = skin
            for ex in (cx - 32, cx + 32):
                if expr == "joy":
                    # happy closed eyes: upward arcs
                    d = math.hypot((x - ex) / 14.0, (y - 236) / 12.0)
                    if 0.75 < d < 1 and y < 236:
                        c = eye
                elif math.hypot((x - ex) / (15.0 if expr == "surprise" else 12.0),
                                (y - 230) / (20.0 if expr == "surprise" else 16.0)) < 1:
                    c = eye
            if expr == "joy":
                d = math.hypot((x - cx) / 28.0, (y - 278) / 16.0)
                if d < 1 and y > 278:
                    c = (200, 90, 110)
            elif expr == "surprise":
                if math.hypot((x - cx) / 11.0, (y - 288) / 14.0) < 1:
                    c = (150, 60, 80)
            elif math.hypot((x - cx) / 18.0, (y - 285) / 5.0) < 1:
                c = (200, 90, 110)
        # bangs
        if 120 < y < 185 and math.hypot((x - cx) / 105.0, (y - 200) / 90.0) < 1 and (y < 150 + 30 * abs(math.sin(x / 22.0))):
            c = hair
        return c + (255,)

    return w, h, px


def main():
    write_png(os.path.join(ROOT, "game", "images", "bg_tavern.png"), 1280, 720, bg_pixel)

    mira = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": "Mira",
            "description": "{{char}} is the barkeep of the Lantern & Thistle, a cozy tavern at a crossroads. "
                           "Silver-haired, sharp-eyed, and quick with a joke, she knows every rumor on the road.",
            "personality": "warm, teasing, curious, secretly sentimental",
            "scenario": "Rain drums on the shutters as {{user}} steps into the Lantern & Thistle late one evening.",
            "first_mes": "*Mira glances up from polishing a mug and grins.* Well, look what the storm dragged in. "
                         "Sit, {{user}}, before you drip on my floor. What'll it be?",
            "mes_example": "<START>\n{{user}}: Any news?\n{{char}}: *She leans on the bar.* News costs a drink, friend.",
            "alternate_greetings": [
                "*The tavern is empty except for Mira, counting coins.* Closing time was an hour ago, {{user}}... "
                "but I suppose one more won't hurt."
            ],
            "tags": ["fantasy", "tavern", "sample"],
            "creator": "Tavern Tales",
            "character_book": {"entries": [
                {"keys": ["lantern"], "content": "The tavern's great lantern never goes out; locals say it's enchanted.",
                 "enabled": True}
            ]},
        },
    }
    payload = base64.b64encode(json.dumps(mira).encode("utf-8")).decode("ascii")
    w, h, px = make_portrait((210, 210, 225), (250, 220, 200), (120, 50, 70), (90, 60, 150))
    write_png(os.path.join(ROOT, "characters", "Mira.png"), w, h, px, [("chara", payload)])

    # SillyTavern-style expression sprites for Mira.
    for expr in ("neutral", "joy", "surprise"):
        w, h, px = make_portrait((210, 210, 225), (250, 220, 200), (120, 50, 70), (90, 60, 150), expr)
        write_png(os.path.join(ROOT, "characters", "Mira", expr + ".png"), w, h, px)

    # A V1-style JSON card with a same-named PNG avatar (no card data inside it).
    rook = {
        "name": "Rook",
        "description": "{{char}} is a weary sellsword nursing a drink in the corner of the tavern.",
        "personality": "gruff, honest, dry humor",
        "scenario": "{{user}} sits down across from a stranger in the tavern's darkest corner.",
        "first_mes": "*Rook doesn't look up.* Seat's taken. *A pause.* ...By you, apparently. Fine.",
        "mes_example": "",
    }
    with open(os.path.join(ROOT, "characters", "Rook.json"), "w") as f:
        json.dump(rook, f, indent=2)
    w, h, px = make_portrait((40, 35, 35), (215, 175, 145), (70, 75, 70), (60, 90, 70))
    write_png(os.path.join(ROOT, "characters", "Rook.png"), w, h, px)
    print("assets written")


if __name__ == "__main__":
    main()
