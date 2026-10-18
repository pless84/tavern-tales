"""Chat files in SillyTavern's .jsonl format (pure Python, no Ren'Py imports).

Line 1 is metadata: {"user_name", "character_name", "create_date", "chat_metadata"}.
Each further line is a message: {"name", "is_user", "is_system", "send_date",
"mes", "swipes"?, "swipe_id"?, "extra"}. Tavern Tales keeps its own extras
(moods) under extra["tavern_tales"], which SillyTavern ignores.
"""

import json
import os
import time


def stamp(t=None):
    return time.strftime("%Y-%m-%d@%Hh%Mm%Ss", time.localtime(t))


def send_date(t=None):
    return time.strftime("%B %d, %Y %I:%M%p", time.localtime(t)).replace(" 0", " ")


def card_key(card):
    """Folder name for a card's chats: the card's file name without extension."""
    path = card.get("path") or ""
    return os.path.splitext(os.path.basename(path))[0] or card.get("name") or "unknown"


def chat_folder(base, card):
    return os.path.join(base, "chats", card_key(card))


def new_chat_path(folder, char_name):
    safe = "".join(ch for ch in char_name if ch not in '\\/:*?"<>|') or "chat"
    return os.path.join(folder, "%s - %s.jsonl" % (safe, stamp()))


def list_chats(folder):
    """Chat files in a folder, newest first."""
    if not folder or not os.path.isdir(folder):
        return []
    files = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(".jsonl")]
    return sorted(files, key=os.path.getmtime, reverse=True)


def to_lines(history, user_name, char_name, create_date=None):
    lines = [{"user_name": user_name, "character_name": char_name,
              "create_date": create_date or stamp(), "chat_metadata": {}}]
    now = send_date()
    for m in history:
        is_user = m["role"] == "user"
        msg = {"name": user_name if is_user else char_name, "is_user": is_user, "is_system": False,
               "send_date": m.get("send_date") or now, "mes": m["content"], "extra": {}}
        if not is_user:
            swipes = m.get("swipes") or [m["content"]]
            msg["swipes"] = list(swipes)
            msg["swipe_id"] = m.get("swipe_id", 0)
            msg["extra"]["tavern_tales"] = {"mood": m.get("mood"), "moods": m.get("moods")}
        lines.append(msg)
    return lines


def from_lines(lines):
    """Parse ST chat lines. Returns (metadata, history). System/narrator messages are skipped."""
    if not lines:
        return {}, []
    meta, history = {}, []
    start = 0
    if isinstance(lines[0], dict) and "mes" not in lines[0]:
        meta, start = lines[0], 1
    for msg in lines[start:]:
        if not isinstance(msg, dict) or msg.get("is_system") or not isinstance(msg.get("mes"), str):
            continue
        date = msg.get("send_date") if isinstance(msg.get("send_date"), str) else None
        if msg.get("is_user"):
            entry = {"role": "user", "content": msg["mes"]}
            if date:
                entry["send_date"] = date
            history.append(entry)
            continue
        raw_swipes = msg.get("swipes")
        swipes = [s for s in (raw_swipes if isinstance(raw_swipes, list) else []) if isinstance(s, str)] or [msg["mes"]]
        sid = msg.get("swipe_id", 0)
        if not isinstance(sid, int) or not 0 <= sid < len(swipes):
            sid = swipes.index(msg["mes"]) if msg["mes"] in swipes else 0
        extra = msg.get("extra")
        tt = extra.get("tavern_tales") if isinstance(extra, dict) else None
        tt = tt if isinstance(tt, dict) else {}
        moods = tt.get("moods")
        if not isinstance(moods, list) or len(moods) != len(swipes):
            moods = [tt.get("mood")] * len(swipes)
        moods = [m if isinstance(m, str) else None for m in moods]
        entry = {"role": "assistant", "content": swipes[sid], "swipes": swipes,
                 "swipe_id": sid, "mood": moods[sid], "moods": moods}
        if date:
            entry["send_date"] = date
        history.append(entry)
    return meta, history


def write_chat(path, history, user_name, char_name, create_date=None):
    """Atomically write a chat file (a crash never leaves a half-written file)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for line in to_lines(history, user_name, char_name, create_date):
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_chat(path):
    lines = []
    with open(path, encoding="utf-8-sig") as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    lines.append(json.loads(raw))
                except ValueError:
                    continue
    return from_lines(lines)


def sillytavern_chat_folders(card, st_character_dirs):
    """Where a SillyTavern install keeps this card's chats (data/<user>/chats/<name>/)."""
    names = {card_key(card), card.get("name") or ""}
    out = []
    for d in st_character_dirs:
        root = os.path.dirname(os.path.normpath(d))
        for n in names:
            if not n or n in (".", "..") or os.path.basename(n) != n or "/" in n or "\\" in n:
                continue
            folder = os.path.join(root, "chats", n)
            if os.path.isdir(folder) and folder not in out:
                out.append(folder)
    return out
