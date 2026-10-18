"""SillyTavern character card loader (pure Python, no Ren'Py imports).

Supports:
  * PNG cards with a tEXt/iTXt/zTXt "chara" (V1/V2) or "ccv3" (V3) chunk
  * Plain .json exports (V1 top-level fields, or V2/V3 with a "data" object)
"""

import base64
import json
import os
import re
import struct
import zlib

from prompting import EXPRESSIONS

PNG_SIG = b"\x89PNG\r\n\x1a\n"
MAX_CARD_BYTES = 32 * 1024 * 1024      # refuse bigger card files
MAX_TEXT_BYTES = 16 * 1024 * 1024      # max inflated size of one text chunk
MAX_IMAGE_SIDE = 8192                  # refuse to decode bigger portraits
WANTED_KEYS = ("chara", "ccv3")
IMAGE_EXTS = (".png", ".webp", ".jpg", ".jpeg")

FIELDS = (
    "name", "description", "personality", "scenario", "first_mes",
    "mes_example", "system_prompt", "post_history_instructions",
    "creator_notes", "creator", "character_version",
)


class CardError(Exception):
    pass


def _inflate(buf, budget):
    """Inflate at most min(MAX_TEXT_BYTES, budget[0]) bytes; budget is a per-file running total."""
    limit = min(MAX_TEXT_BYTES, budget[0])
    if limit <= 0:
        # zlib treats max_length=0 as "unlimited", so never pass it.
        raise CardError("compressed text too large")
    d = zlib.decompressobj()
    out = d.decompress(buf, limit)
    if d.unconsumed_tail or (len(out) >= limit and not d.eof):
        raise CardError("compressed text too large")
    budget[0] -= len(out)
    return out


def png_text_chunks(data, wanted=WANTED_KEYS):
    """Return {keyword_lower: text} for the wanted text chunks in a PNG."""
    if not data.startswith(PNG_SIG):
        raise CardError("not a PNG file")

    out = {}
    budget = [MAX_TEXT_BYTES * 2]   # total inflated bytes allowed for the whole file
    pos = len(PNG_SIG)
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length

        if ctype in (b"tEXt", b"zTXt", b"iTXt"):
            key = body.partition(b"\0")[0].decode("latin-1").lower()
            if wanted and key not in wanted:
                continue
        if ctype == b"tEXt":
            key, _, text = body.partition(b"\0")
            out[key.decode("latin-1").lower()] = text.decode("latin-1")
        elif ctype == b"zTXt":
            key, _, rest = body.partition(b"\0")
            out[key.decode("latin-1").lower()] = _inflate(rest[1:], budget).decode("latin-1")
        elif ctype == b"iTXt":
            key, _, rest = body.partition(b"\0")
            if len(rest) < 2:
                continue
            compressed = rest[0]
            rest = rest[2:]
            _lang, _, rest = rest.partition(b"\0")
            _tkey, _, text = rest.partition(b"\0")
            if compressed:
                text = _inflate(text, budget)
            out[key.decode("latin-1").lower()] = text.decode("utf-8")
        elif ctype == b"IEND":
            break
    return out


def image_size_ok(path):
    """False for PNGs whose header declares a huge image (decoding would exhaust memory)."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        if head.startswith(PNG_SIG) and head[12:16] == b"IHDR":
            w, h = struct.unpack(">II", head[16:24])
            return w <= MAX_IMAGE_SIDE and h <= MAX_IMAGE_SIDE
        return os.path.getsize(path) <= MAX_CARD_BYTES
    except OSError:
        return False


def _str(v):
    return v if isinstance(v, str) else ""


def _decode_payload(text):
    """Card payloads are usually base64 JSON, occasionally raw JSON."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    return json.loads(base64.b64decode(text + "=" * (-len(text) % 4)).decode("utf-8"))


def normalize(raw):
    """Flatten V1/V2/V3 card JSON into one plain dict."""
    if not isinstance(raw, dict):
        raise CardError("card JSON is not an object")

    src = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    card = {}
    for f in FIELDS:
        val = src.get(f, raw.get(f, ""))
        card[f] = val if isinstance(val, str) else ""

    # Old exports sometimes use "char_name"/"char_persona"/"world_scenario"/"char_greeting".
    card["name"] = (card["name"] or _str(raw.get("char_name")) or "Unnamed").strip()[:100] or "Unnamed"
    card["personality"] = card["personality"] or _str(raw.get("char_persona"))
    card["scenario"] = card["scenario"] or _str(raw.get("world_scenario"))
    card["first_mes"] = card["first_mes"] or _str(raw.get("char_greeting"))
    card["mes_example"] = card["mes_example"] or _str(raw.get("example_dialogue"))

    alts = src.get("alternate_greetings")
    alts = alts if isinstance(alts, list) else []
    card["alternate_greetings"] = [a for a in alts if isinstance(a, str) and a.strip()]
    tags = src.get("tags")
    tags = tags if isinstance(tags, list) else []
    card["tags"] = [t for t in tags if isinstance(t, str)]

    book = src.get("character_book")
    card["lorebook"] = []
    if isinstance(book, dict):
        entries = book.get("entries")
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict) or e.get("enabled") is False:
                continue
            ekeys = e.get("keys")
            keys = [k.lower() for k in (ekeys if isinstance(ekeys, list) else []) if isinstance(k, str) and k]
            card["lorebook"].append({
                "keys": keys,
                "content": _str(e.get("content")),
                "constant": bool(e.get("constant")),
            })

    card["spec"] = raw.get("spec", "chara_card_v1")
    return card


def load_card(path):
    """Load one card file. Returns a normalized dict with 'path' and 'avatar'."""
    ext = os.path.splitext(path)[1].lower()
    if os.path.getsize(path) > MAX_CARD_BYTES:
        raise CardError("file too large")
    with open(path, "rb") as f:
        data = f.read()

    if ext == ".json":
        try:
            raw = json.loads(data.decode("utf-8-sig"))
        except ValueError as e:
            raise CardError("bad JSON: %s" % e)
        card = normalize(raw)
        card["avatar"] = _sibling_image(path)
    elif ext == ".png":
        chunks = png_text_chunks(data)
        payload = chunks.get("ccv3") or chunks.get("chara")
        if not payload:
            raise CardError("PNG has no character data")
        try:
            card = normalize(_decode_payload(payload))
        except (ValueError, UnicodeDecodeError) as e:
            raise CardError("could not decode card data: %s" % e)
        card["avatar"] = path
    else:
        raise CardError("unsupported file type")

    card["path"] = path
    return card


def safe_folder_name(n):
    """True for a plain single folder name (no path separators, no '..')."""
    return bool(n) and n not in (".", "..") and os.path.basename(n) == n and not os.path.isabs(n) \
        and "/" not in n and "\\" not in n


def _sibling_image(path):
    stem = os.path.splitext(path)[0]
    for ext in IMAGE_EXTS:
        if os.path.exists(stem + ext):
            return stem + ext
    return None


def scan(dirs):
    """Scan folders for cards. Returns (cards, errors) where errors is [(path, msg)]."""
    cards, errors, seen = [], [], set()
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d), key=str.lower):
            path = os.path.join(d, name)
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".png", ".json") or not os.path.isfile(path):
                continue
            # A .png next to a same-named .json is that JSON's avatar, not a card.
            if ext == ".png" and os.path.exists(os.path.splitext(path)[0] + ".json"):
                continue
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            try:
                cards.append(load_card(path))
            except Exception as e:
                errors.append((path, str(e)))
    return cards, errors


_MACROS = [
    (re.compile(r"\{\{char\}\}|<BOT>", re.I), "char"),
    (re.compile(r"\{\{user\}\}|<USER>", re.I), "user"),
]


def apply_macros(text, char, user, persona=""):
    if not text:
        return ""
    for rx, kind in _MACROS:
        value = char if kind == "char" else user
        text = rx.sub(lambda m, v=value: v, text)
    text = re.sub(r"\{\{persona\}\}", lambda m: persona, text, flags=re.I)
    return re.sub(r"\{\{(original|trim)\}\}", "", text, flags=re.I)


def detect_sillytavern_dirs():
    """Best-effort search for a local SillyTavern install's character folders."""
    home = os.path.expanduser("~")
    roots = [os.path.join(home, "SillyTavern")]
    for parent in (home, os.path.join(home, "Projects"), os.path.join(home, "Games"),
                   os.path.join(home, "apps"), os.path.join(home, ".local", "share")):
        if os.path.isdir(parent):
            try:
                for n in os.listdir(parent):
                    if n.lower().startswith("sillytavern"):
                        roots.append(os.path.join(parent, n))
            except OSError:
                pass

    found = []
    for root in roots:
        data = os.path.join(root, "data")
        if os.path.isdir(data):
            for user in os.listdir(data):
                c = os.path.join(data, user, "characters")
                if os.path.isdir(c):
                    found.append(c)
        legacy = os.path.join(root, "public", "characters")
        if os.path.isdir(legacy):
            found.append(legacy)
    return found


SPRITE_EXTS = (".png", ".webp", ".jpg", ".jpeg", ".gif")


def find_expressions(card, dirs):
    """SillyTavern expression sprites for a card: {label: path}.

    Looks for a folder named after the card (or its file name) inside each
    characters folder, e.g. characters/Mira/joy.png. The first folder with any
    sprites wins, so the game's own folder overrides a SillyTavern install.
    """
    names = [card.get("name") or ""]
    if card.get("path"):
        names.append(os.path.splitext(os.path.basename(card["path"]))[0])
    for d in dirs:
        for n in names:
            folder = os.path.join(d, n) if safe_folder_name(n) else None
            if not folder or not os.path.isdir(folder):
                continue
            found = {}
            for f in sorted(os.listdir(folder)):
                stem, ext = os.path.splitext(f)
                label = stem.lower()
                if ext.lower() in SPRITE_EXTS and label in EXPRESSIONS and label not in found:
                    found[label] = os.path.join(folder, f)
            if found:
                return found
    return {}
