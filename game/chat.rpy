# Card library, prompt building and the LLM client.

default persistent.api_base = "http://127.0.0.1:11434/v1"
default persistent.api_key = ""
default persistent.model = ""
default persistent.user_name = ""
default persistent.temperature = 0.8
default persistent.max_tokens = 350
default persistent.context_tokens = 4096
default persistent.mood_mode = "keywords"   # "keywords", "model" or "off"
default persistent.extra_card_dirs = []
default persistent.persona = ""
default persistent.text_size = 24

# Current session state (saved with the game).
default card = None
default history = []
default card_name = ""
default stream_id = None
default current_expression = None
default chat_file = None
default chat_created = None
default current_sprite = None

init -10 python:
    import os, re, sys, subprocess
    import stcards, prompting, llmstream, chatlog

    CHAT_TEMPLATE = (
        "Write {{char}}'s next reply in a fictional roleplay chat between {{char}} and {{user}}. "
        "Stay in character. Write actions in *asterisks* and speech in plain text. "
        "Keep replies to one to three short paragraphs and never write {{user}}'s lines."
    )

    def user_name():
        return persistent.user_name or "You"

    def cards_dir():
        d = os.path.join(config.basedir, "characters")
        if not os.path.isdir(d):
            try:
                os.makedirs(d)
            except OSError:
                pass
        return d

    def card_dirs():
        dirs = [cards_dir()] + list(persistent.extra_card_dirs or [])
        if os.environ.get("TT_NO_ST_DETECT"):
            return dirs
        for d in stcards.detect_sillytavern_dirs():
            if d not in dirs:
                dirs.append(d)
        return dirs

    def scan_cards():
        return stcards.scan(card_dirs())

    def open_folder(path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            renpy.notify("Could not open folder: %s" % e)

    def add_card_dir(path):
        path = os.path.expanduser(path.strip())
        if not os.path.isdir(path):
            renpy.notify("Not a folder: %s" % path)
            return
        if path not in persistent.extra_card_dirs:
            persistent.extra_card_dirs = persistent.extra_card_dirs + [path]
        renpy.notify("Added %s" % path)

    # ---- Portraits -------------------------------------------------------

    # Decoded images live on the stcards module, so they're never pickled into saves.
    stcards._image_cache = {}

    def _portrait_image(path):
        cache = stcards._image_cache
        if path not in cache:
            if len(cache) > 64:
                cache.clear()
            try:
                if not stcards.image_size_ok(path):
                    raise ValueError("image too large")
                with open(path, "rb") as f:
                    cache[path] = im.Data(f.read(), os.path.basename(path))
            except Exception:
                cache[path] = Solid("#0000")
        return cache[path]

    class Portrait(renpy.Displayable):
        """A card avatar. Saves only the file path, never the image bytes."""

        def __init__(self, path, w, h, expression=None, **kwargs):
            super(Portrait, self).__init__(**kwargs)
            self.path = path
            self.w = w
            self.h = h
            self.expression = expression

        def _child(self):
            if not self.path:
                return Text("?", size=int(self.h * 0.4), color="#ffffff55", xalign=0.5, yalign=0.5)
            return Transform(_portrait_image(self.path), fit="contain", xsize=self.w, ysize=self.h)

        def render(self, width, height, st, at):
            return renpy.render(self._child(), width, height, st, at)

        def visit(self):
            return [self._child()]

        def _key(self):
            return (self.path, self.w, self.h, getattr(self, "expression", None))

        def __eq__(self, other):
            return type(other) is Portrait and self._key() == other._key()

        def __hash__(self):
            return hash(self._key())

    def _portrait_dd(st, at, path, w, h):
        """Kept so saves from v0.1.0 (which used DynamicDisplayable) still load."""
        return Portrait(path, w, h), None

    def portrait(path, w=560, h=700, expression=None):
        return Portrait(path, w, h, expression)

    # ---- Preferences -----------------------------------------------------

    def apply_text_size():
        style.say_text.size = int(persistent.text_size or 24)
        style.rebuild()

    # ---- Expressions -----------------------------------------------------

    def load_expressions():
        """Attach SillyTavern expression sprites to the current card."""
        card["expressions"] = stcards.find_expressions(card, card_dirs())

    def sprite_for(mood):
        """(label, path) of the sprite to show for a mood, falling back to neutral, then the avatar."""
        sprites = (card or {}).get("expressions") or {}
        for label in (mood, "neutral"):
            if label and label in sprites:
                return label, sprites[label]
        return None, (card or {}).get("avatar")

    def show_mood(mood):
        if persistent.mood_mode == "off" or not card:
            return
        label, path = sprite_for(mood)
        if (label, path) == (store.current_expression, store.current_sprite):
            return
        store.current_expression, store.current_sprite = label, path
        renpy.show("char", what=portrait(path, expression=label), at_list=[portrait_still])
        renpy.with_statement(Dissolve(0.2))

    # ---- Text helpers ----------------------------------------------------

    def macros(text):
        return stcards.apply_macros(text, card["name"] if card else "", user_name(), persistent.persona or "")

    def escape_renpy(text):
        return text.replace("{", "{{").replace("[", "[[")

    def italicize(escaped):
        """*action* -> {i}action{/i} on text that is already escaped."""
        return re.sub(r"\*([^*\n]+)\*", r"{i}\1{/i}", escaped)

    THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)

    def clean_reply(text):
        text = THINK_RE.sub("", text)
        text = text.strip()
        # Strip a leading "Name:" the model sometimes adds.
        if card and text.lower().startswith(card["name"].lower() + ":"):
            text = text[len(card["name"]) + 1:].lstrip()
        # Cut off anything where the model starts writing for the user.
        cut = re.search(r"\n\s*" + re.escape(user_name()) + r"\s*:", text)
        if cut:
            text = text[:cut.start()]
        return text.strip()

    def _chunk_limit():
        """Characters that fit the textbox at the current dialogue text size."""
        size = max(16, int(persistent.text_size or 24))
        return max(120, int(380 * (24.0 / size) ** 2))

    def _chunks(par, limit=None):
        """Split a long paragraph into sentence groups that fit the textbox."""
        limit = limit or _chunk_limit()
        if len(par) <= limit:
            return [par]
        out, cur = [], ""
        for s in re.split(r"(?<=[.!?…\"])\s+", par):
            if cur and len(cur) + len(s) > limit:
                out.append(cur)
                cur = s
            else:
                cur = (cur + " " + s).strip()
        if cur:
            out.append(cur)
        return out

    def add_reply(text, mood, as_swipe=False):
        """Record an assistant reply. Each entry keeps its swipes and the active one in 'content'."""
        if as_swipe and history and history[-1]["role"] == "assistant":
            e = history[-1]
            e.setdefault("swipes", [e["content"]])
            e.setdefault("moods", [e.get("mood", "neutral")] * len(e["swipes"]))
            e["swipes"].append(text)
            e["moods"].append(mood)
            e["swipe_id"] = len(e["swipes"]) - 1
            e["content"], e["mood"] = text, mood
        else:
            history.append({"role": "assistant", "content": text, "mood": mood,
                            "swipes": [text], "moods": [mood], "swipe_id": 0,
                            "send_date": chatlog.send_date()})

    # ---- Chat files (SillyTavern .jsonl) ------------------------------------

    def chat_dir():
        return chatlog.chat_folder(config.basedir, card)

    def st_chat_files():
        if os.environ.get("TT_NO_ST_DETECT"):
            return []
        folders = chatlog.sillytavern_chat_folders(card, stcards.detect_sillytavern_dirs())
        return [f for d in folders for f in chatlog.list_chats(d)]

    def save_chat():
        if not card or not store.chat_file or not any(m["role"] == "user" for m in history):
            return
        try:
            chatlog.write_chat(store.chat_file, history, user_name(), card_name, store.chat_created)
        except Exception as e:
            renpy.notify("Couldn't save the chat file: %s" % e)

    def new_chat():
        store.chat_file = chatlog.new_chat_path(chat_dir(), card_name)
        store.chat_created = chatlog.stamp()

    def open_chat(path, copy=False):
        """Load a chat file into history. copy=True imports it as a new chat of our own."""
        try:
            meta, hist = chatlog.read_chat(path)
        except Exception as e:
            renpy.notify("Couldn't read that chat: %s" % e)
            meta, hist = {}, []
        # Copy into Ren'Py's own (save/rollback-aware) dict and list types.
        store.history = [dict(m, **{k: list(m[k]) for k in ("swipes", "moods") if k in m}) for m in hist]
        if copy:
            new_chat()
            save_chat()
        else:
            store.chat_file = path
            store.chat_created = meta.get("create_date")

    def _chat_on_disk_is_ahead():
        """True if the chat file holds messages this (loaded) history doesn't have."""
        try:
            _, on_disk = chatlog.read_chat(store.chat_file)
        except Exception:
            return False
        if len(on_disk) > len(history):
            return True
        return [m["content"] for m in on_disk] != [m["content"] for m in history[:len(on_disk)]]

    def _after_load():
        # A stream from before the load isn't ours any more.
        s = llmstream.CURRENT
        if s is not None and s.id != store.stream_id:
            s.cancel()
        if not card:
            return
        if not store.chat_file:
            new_chat()          # saves from v0.1.0 had no chat file
        elif os.path.exists(store.chat_file) and _chat_on_disk_is_ahead():
            new_chat()          # loading an older save: branch instead of overwriting newer messages

    config.after_load_callbacks.append(_after_load)

    def _cancel_streams():
        if llmstream.CURRENT is not None:
            llmstream.CURRENT.cancel()

    config.start_callbacks.append(_cancel_streams)

    def log_entries():
        """(name, display text, is_user) for every message, for the chat log screen."""
        out = []
        for m in history:
            is_user = m["role"] == "user"
            who = user_name() if is_user else card_name
            line = italicize(escape_renpy(m["content"]))
            n = len(m.get("swipes") or [])
            if n > 1:
                line += "  {size=15}{color=#b9aedc}(swipe %d/%d){/color}{/size}" % (m.get("swipe_id", 0) + 1, n)
            out.append((escape_renpy(who), line, is_user))
        return out

    def swipe_info():
        """(index, total) for the last assistant message, or None if there's nothing to swipe."""
        if len(history) < 2 or history[-1]["role"] != "assistant":
            return None
        e = history[-1]
        return e.get("swipe_id", 0), len(e.get("swipes") or [e["content"]])

    def switch_swipe(delta):
        """Show another stored swipe of the last assistant message."""
        e = history[-1]
        swipes = e.get("swipes") or [e["content"]]
        moods = e.get("moods") or [e.get("mood")] * len(swipes)
        i = max(0, min(len(swipes) - 1, e.get("swipe_id", 0) + delta))
        e["swipe_id"], e["content"], e["mood"] = i, swipes[i], moods[i]

    def say_reply(text, mood=None):
        """Show a reply VN-style: *action* paragraphs go to the narrator."""
        show_mood(mood)
        who = store.bot
        for par in re.split(r"\n+", text):
            par = par.strip()
            if not par:
                continue
            for piece in _chunks(par):
                if re.fullmatch(r"\*[^*]+\*", piece):
                    renpy.say(narrator, escape_renpy(piece.strip("*").strip()))
                else:
                    shown = italicize(escape_renpy(piece))
                    renpy.say(who, shown)

    # ---- Prompt ----------------------------------------------------------

    def _lore(recent):
        if not card or not card.get("lorebook"):
            return ""
        hay = " ".join(m["content"] for m in recent).lower()
        hits = [e["content"] for e in card["lorebook"]
                if e["content"] and (e["constant"] or any(k in hay for k in e["keys"]))]
        return "\n".join(hits)

    def build_messages(exclude_last=False):
        """System prompt + as much recent history as fits persistent.context_tokens."""
        c = card
        hist = list(history[:-1] if exclude_last else history)
        core = [c.get("system_prompt") or CHAT_TEMPLATE]
        if persistent.mood_mode == "model":
            core.append(prompting.MOOD_INSTRUCTION)
        if c["description"]:
            core.append(c["description"])
        if c["personality"]:
            core.append("{{char}}'s personality: " + c["personality"])
        if c["scenario"]:
            core.append("Scenario: " + c["scenario"])
        if (persistent.persona or "").strip():
            core.append("{{user}}'s persona: " + persistent.persona.strip())
        parts = [("core", macros("\n\n".join(core)))]
        lore = _lore(hist[-4:])
        if lore:
            parts.append(("lore", macros(lore)))
        if c["mes_example"]:
            ex = re.sub(r"<START>", "", c["mes_example"], flags=re.I).strip()
            parts.append(("example", macros("Example dialogue:\n" + ex)))
        post = macros(c.get("post_history_instructions") or "")

        ctx = int(persistent.context_tokens)
        max_tok = min(int(persistent.max_tokens), ctx // 2)
        # The system prompt may use at most half the room left after the reply.
        parts = prompting.fit_system(parts, max(256, (ctx - max_tok) // 2))
        system = "\n\n".join(t for _, t in parts)
        used = prompting.estimate_tokens(system) + (prompting.estimate_tokens(post) if post else 0)
        recent = prompting.trim_history(hist, prompting.history_budget(ctx, max_tok, used))

        msgs = [{"role": "system", "content": system}]
        msgs += [{"role": m["role"], "content": m["content"]} for m in recent]
        if post:
            msgs.append({"role": "system", "content": post})
        return msgs

    # ---- LLM client (OpenAI-compatible /chat/completions) ---------------

    API_PRESETS = [
        ("KoboldCpp", "http://127.0.0.1:5001/v1"),
        ("Ollama", "http://127.0.0.1:11434/v1"),
        ("LM Studio", "http://127.0.0.1:1234/v1"),
        ("text-gen-webui", "http://127.0.0.1:5000/v1"),
        ("OpenRouter", "https://openrouter.ai/api/v1"),
        ("OpenAI", "https://api.openai.com/v1"),
    ]

    def _headers():
        h = {"Content-Type": "application/json"}
        if persistent.api_key:
            h["Authorization"] = "Bearer " + persistent.api_key
        return h

    def insecure_key_warning():
        """Warn when an API key would be sent in clear text to a non-local server."""
        base = (persistent.api_base or "").lower()
        if not persistent.api_key or not base.startswith("http://"):
            return ""
        host = re.sub(r"^http://(\[[^\]]*\]|[^/:]+).*", r"\1", base)
        if host in ("127.0.0.1", "localhost", "[::1]"):
            return ""
        return "Warning: your API key would be sent unencrypted (http://) to %s." % host

    def _url(path):
        return persistent.api_base.rstrip("/") + path

    def _payload(exclude_last=False):
        payload = {
            "messages": build_messages(exclude_last),
            "temperature": float(persistent.temperature),
            "max_tokens": min(int(persistent.max_tokens), int(persistent.context_tokens) // 2),
            "stop": ["\n" + user_name() + ":"],
        }
        if not persistent.model:
            test_connection()  # fills in the first model the backend lists
        if persistent.model:
            payload["model"] = persistent.model
        return payload

    def start_reply(exclude_last=False):
        """Start streaming the next reply. The stream itself lives on llmstream, never in saves."""
        s = llmstream.start(_url("/chat/completions"), _payload(exclude_last), _headers())
        store.stream_id = s.id

    def current_stream():
        return llmstream.get(store.stream_id)

    def cancel_reply():
        s = current_stream()
        if s is not None:
            s.cancel()

    def stream_tick():
        """Timer action for the streaming screen: ends the interaction when there's news."""
        s = current_stream()
        if s is None:
            return "lost"       # e.g. we were loaded from a save made mid-request
        if s.done:
            return "done"
        renpy.restart_interaction()
        return None

    def _mmss(sec):
        sec = int(sec)
        return "%d:%02d" % (sec // 60, sec % 60)

    def stream_view():
        """(status line, live text) for the streaming screen."""
        s = current_stream()
        if s is None:
            return "", ""
        text = re.sub(r"\[\s*mood[^\]]*\]?\s*$", "", s.snapshot(), flags=re.I)
        text = THINK_RE.sub("", text).strip()
        if not text:
            return "%s is typing… %s" % (escape_renpy(card_name), _mmss(s.elapsed())), ""
        limit = _chunk_limit()
        if len(text) > limit:
            text = "…" + text[-limit:].split(" ", 1)[-1]
        shown = italicize(escape_renpy(text))
        return "", shown

    def finish_reply():
        """Returns (text, error, mood). (None, None, None) means there is no stream to read."""
        s = current_stream()
        if s is None or not s.done:
            return None, None, None
        if s.error:
            return None, s.error, None
        text, tag = prompting.extract_mood_tag(s.text)
        text = clean_reply(text)
        if not text:
            return None, "The model returned an empty reply.", None
        mood = tag or prompting.classify_mood(text)
        return text, None, mood

    def detect_context():
        """Ask Ollama for the model's context size (num_ctx). Returns a status message."""
        base = re.sub(r"/v1/?$", "", persistent.api_base.rstrip("/"))
        try:
            data = renpy.fetch(base + "/api/show", method="POST", json={"model": persistent.model},
                               headers=_headers(), timeout=15, result="json")
        except Exception as e:
            return "Couldn't detect context size (Ollama only): %s" % e
        m = re.search(r"num_ctx\s+(\d+)", data.get("parameters") or "")
        if not m:
            return "This model has no num_ctx set, so Ollama's default applies; context size unchanged."
        n = int(m.group(1))
        persistent.context_tokens = max(1024, min(32768, n))
        return "Context size set to %d tokens." % persistent.context_tokens

    def test_connection():
        try:
            data = renpy.fetch(_url("/models"), headers=_headers(), timeout=15, result="json")
            ids = [m.get("id", "?") for m in data.get("data", [])]
            if ids and not persistent.model:
                persistent.model = ids[0]
            return "Connected. Models: " + (", ".join(ids[:6]) or "(none listed)")
        except Exception as e:
            return "Failed: %s" % e
