# Automated tests. Run everything with:  bash tools/check.sh
# (check.sh runs these on a temporary copy of the project against tools/mock_llm.py.)

init python:
    import json, re

    # Ren'Py drops mouse clicks while the OS says the window lacks mouse focus,
    # i.e. whenever the real pointer is elsewhere on the desktop. Tests click
    # with a virtual mouse, so keep the flag set while a test is running.
    def _tt_keep_mouse_focus():
        if renpy.is_in_test():
            renpy.display.interface.mouse_focused = True

    config.periodic_callbacks.append(_tt_keep_mouse_focus)

init python in tt_test:
    import json, os
    import store
    import urllib.request

    MOCK = os.environ.get("TT_MOCK_URL", "http://127.0.0.1:8799")

    def _post(path, body):
        req = urllib.request.Request(MOCK + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def mock(**knobs):
        return _post("/_config", knobs)

    def reset():
        return _post("/_reset", {})

    def log():
        with urllib.request.urlopen(MOCK + "/_log", timeout=5) as r:
            return json.loads(r.read())

    def last_request():
        entries = log()
        return entries[-1]["request"] if entries else {}

    def partial(full):
        s = store.current_stream()
        return s is not None and 0 < len(s.snapshot()) < len(full)

    def requests_made():
        return len(log())

    def make_big_png():
        """A ~1 MB valid PNG (Mira's portrait plus a padding chunk), inside the temp project."""
        import struct, zlib
        src = open(os.path.join(store.config.basedir, "characters", "Mira.png"), "rb").read()
        pad = os.urandom(1024 * 1024)
        chunk = struct.pack(">I", len(pad)) + b"zzPd" + pad + struct.pack(">I", zlib.crc32(b"zzPd" + pad) & 0xFFFFFFFF)
        i = src.rindex(b"IEND") - 4
        path = os.path.join(store.config.basedir, "big_portrait.png")
        open(path, "wb").write(src[:i] + chunk + src[i:])
        return path

    def save_size(slot):
        import glob
        files = glob.glob(os.path.join(store.config.savedir, "1-%s-*.save" % slot))
        return os.path.getsize(files[0]) if files else -1

    def in_test_root():
        root = os.environ.get("TT_TEST_ROOT")
        return bool(root) and os.path.realpath(store.config.basedir) == os.path.realpath(root)

    EVIL_NAME = "Evil[setattr(store, 'pwned', True)]{b}X"

    def write_evil_card():
        assert in_test_root()
        path = os.path.join(store.config.basedir, "characters", "evil.json")
        with open(path, "w") as f:
            json.dump({"name": EVIL_NAME, "description": "x", "first_mes": "Hi {a=jump:start}click{/a} [persistent.api_key]"}, f)
        return path

    def chat_len(path):
        return len(store.chatlog.read_chat(path)[1])

    def clear_chats():
        """Delete chat files, but only inside check.sh's temporary project copy."""
        import shutil
        base = os.path.realpath(store.config.basedir)
        root = os.environ.get("TT_TEST_ROOT")
        if root and base == os.path.realpath(root):
            shutil.rmtree(os.path.join(base, "chats"), ignore_errors=True)

    def system_prompt():
        msgs = last_request().get("messages", [])
        return msgs[0]["content"] if msgs else ""

# Test entry point: clean chat state, then the normal game flow.
label tt_begin:
    $ card = None
    $ history = []
    $ card_name = ""
    jump start

testsuite global:
    setup:
        pause 1.0

    before testcase:
        $ tt_test.reset()
        $ tt_test.clear_chats()
        $ persistent.api_base = tt_test.MOCK + "/v1"
        $ persistent.model = ""
        $ persistent.user_name = "Sam"
        $ persistent.persona = ""
        $ persistent.mood_mode = "keywords"

    after testcase:
        $ llmstream.CURRENT and llmstream.CURRENT.cancel()

    teardown:
        $ persistent.api_base = "http://127.0.0.1:11434/v1"
        $ persistent.model = ""
        exit

    testcase smoke:
        description "Name prompt, pick Mira, choose greeting, send a message, get the mock reply."
        $ persistent.user_name = ""
        run Jump("tt_begin")
        pause until screen "input" timeout 10.0
        type "Sam"
        keysym "K_RETURN"
        pause until screen "card_picker" timeout 10.0
        screenshot "smoke_1_picker.png"
        click id "card_Mira" until not screen "card_picker" timeout 10.0
        advance until screen "choice" timeout 20.0
        click "Greeting 1" until not screen "choice" timeout 10.0
        advance until screen "chat_input" timeout 20.0
        assert eval (persistent.user_name == "Sam")
        assert eval (len(store.history) == 1)
        type "Hi Mira! Tell me about the lantern."
        click "Send" until not screen "chat_input" timeout 10.0
        advance until screen "chat_input" timeout 60.0
        assert eval (store.history[-1]["role"] == "assistant")
        assert eval ("Hello there" in store.history[-1]["content"])
        assert eval ("enchanted" in tt_test.system_prompt())
        assert eval ("{{" not in tt_test.system_prompt())
        screenshot "smoke_2_chat.png"

    testcase rook_no_sprites:
        description "A card without expression sprites keeps its avatar."
        run Jump("tt_begin")
        pause until screen "card_picker" timeout 10.0
        click id "card_Rook" until not screen "card_picker" timeout 10.0
        advance until screen "chat_input" timeout 20.0
        type "Hello"
        click "Send" until not screen "chat_input" timeout 10.0
        advance until screen "chat_input" timeout 20.0
        assert eval (store.current_expression is None and store.current_sprite.endswith("Rook.png"))
        assert eval ("Hello there" in store.history[-1]["content"])

    testcase prefs:
        description "Preferences screen changes text speed and dialogue size."
        run Jump("tt_begin")
        pause until screen "card_picker" timeout 10.0
        run ShowMenu("preferences")
        assert screen "preferences" timeout 5.0
        $ tt_test.cps0 = preferences.text_cps
        click id "text_speed_bar" pos (0.2, 0.5)
        assert eval (preferences.text_cps != tt_test.cps0) timeout 2.0
        click id "text_size_bar" pos (0.95, 0.5)
        assert eval (persistent.text_size >= 30 and style.say_text.size == persistent.text_size) timeout 2.0
        pause 0.3
        screenshot "prefs_1.png"
        $ persistent.text_size = 24
        $ apply_text_size()
        $ preferences.text_cps = tt_test.cps0
        keysym "K_ESCAPE"
        assert not screen "preferences" timeout 5.0

    testcase settings_layout:
        description "AI Settings renders with every row on screen."
        run Jump("tt_begin")
        pause until screen "card_picker" timeout 10.0
        click "AI Settings" until screen "ai_settings_screen" timeout 10.0
        pause 0.3
        screenshot "settings_1.png"
        click "Done" until not screen "ai_settings_screen" timeout 10.0

    testcase model_picker:
        description "Choose… lists the server's models and sets the picked one."
        $ persistent.model = ""
        run Jump("tt_begin")
        pause until screen "card_picker" timeout 10.0
        click "AI Settings" until screen "ai_settings_screen" timeout 10.0
        click id "choose_model" until screen "model_picker" timeout 10.0
        pause 0.3
        screenshot "models_1.png"
        assert screen "model_picker"
        click id "model_tiny-model:7b" until not screen "model_picker" timeout 10.0
        assert eval (persistent.model == "tiny-model:7b")
        click "Done" until not screen "ai_settings_screen" timeout 10.0
        $ persistent.model = ""

    testcase evil_card_name:
        description "A card name with [expr] and {tags} is shown literally and never evaluated."
        $ tt_test.evil = tt_test.write_evil_card()
        run Jump("tt_begin")
        pause until screen "card_picker" timeout 10.0
        click id ("card_" + tt_test.EVIL_NAME) until not screen "card_picker" timeout 10.0
        advance until screen "chat_input" timeout 20.0
        $ tt_test.mock(delay=2)
        type "Hello"
        click "Send" until not screen "chat_input" timeout 10.0
        pause 0.8
        assert eval ("Evil[[setattr" in store.stream_view()[0])
        screenshot "evil_1.png"
        advance until screen "chat_input" timeout 20.0
        assert eval (not getattr(store, "pwned", False))
        $ os.remove(tt_test.evil)

    testsuite chat:
        description "Tests that start in a chat with Mira (greeting 1 shown)."
        before testcase:
            run Jump("tt_begin")
            pause until screen "card_picker" timeout 10.0
            click id "card_Mira" until not screen "card_picker" timeout 10.0
            advance until screen "choice" timeout 20.0
            click "Greeting 1" until not screen "choice" timeout 10.0
            advance until screen "chat_input" timeout 20.0

        testcase stream_basic:
            $ tt_test.LONG = "*She leans on the bar.* " + " ".join("word%02d" % i for i in range(60)) + "."
            $ tt_test.mock(reply=tt_test.LONG, chunk_delay=0.15)
            type "Tell me a long story."
            click "Send" until not screen "chat_input" timeout 10.0
            pause until eval tt_test.partial(tt_test.LONG) timeout 10.0
            pause 1.0
            assert eval (store.stream_view()[1] != "" and tt_test.partial(tt_test.LONG))
            screenshot "stream_1_partial.png"
            advance until screen "chat_input" timeout 30.0
            assert eval (store.history[-1]["content"] == tt_test.LONG)
            assert eval (tt_test.last_request().get("stream") is True)

        testcase stream_cancel:
            $ tt_test.mock(delay=30)
            type "Are you there?"
            click "Send" until not screen "chat_input" timeout 10.0
            pause 2.0
            screenshot "stream_2_waiting.png"
            click id "cancel_reply" until not screen "streaming_reply" timeout 10.0
            assert screen "chat_input" timeout 1.0
            assert eval (store.history[-1]["role"] == "user" and store.history[-1]["content"] == "Are you there?")
            assert eval tt_test.log()[-1]["disconnected"] timeout 2.0

        testcase stream_indicator:
            $ tt_test.mock(delay=5)
            type "Hello?"
            click "Send" until not screen "chat_input" timeout 10.0
            pause 3.0
            assert eval (re.search(r"typing… 0:0[2-5]$", store.stream_view()[0]) is not None)
            advance until screen "chat_input" timeout 30.0
            assert eval ("Hello there" in store.history[-1]["content"])

        testcase load_mid_stream:
            $ tt_test.mock(delay=4)
            type "Wait for it."
            click "Send" until not screen "chat_input" timeout 10.0
            pause 1.0
            run FileSave(1, confirm=False)
            pause 0.5
            # Forget the running stream, like a fresh launch would.
            $ llmstream.CURRENT.cancel()
            $ llmstream.CURRENT = None
            run FileLoad(1, confirm=False)
            advance until screen "chat_input" timeout 40.0
            assert eval ("Hello there" in store.history[-1]["content"])
            assert eval (tt_test.requests_made() == 2)

        testcase non_stream_fallback:
            $ tt_test.mock(stream_mode="never", reply="Plain reply here.")
            type "Hi"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.history[-1]["content"] == "Plain reply here.")

        testcase error_then_retry:
            $ tt_test.mock(status=500)
            type "Hi"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until "mock failure" timeout 20.0
            advance until screen "chat_input" timeout 20.0
            $ tt_test.mock(status=200)
            click "Retry" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval ("Hello there" in store.history[-1]["content"])

        testcase expressions:
            assert eval (set(store.card["expressions"]) >= {"neutral", "joy", "surprise"})
            $ tt_test.mock(reply="*She laughs brightly* That's wonderful!")
            type "I brought you a gift."
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.current_expression == "joy" and store.current_sprite.endswith("joy.png"))
            assert eval (store.history[-1]["mood"] == "joy")
            pause 0.5
            screenshot "expr_1_joy.png"
            $ tt_test.mock(reply="*Her eyes go wide and she gasps.* No way!")
            type "I'm a dragon."
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.current_expression == "surprise")
            $ persistent.mood_mode = "model"
            $ tt_test.mock(reply="Fine, fine. [mood: joy]")
            type "Just kidding."
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.current_expression == "joy" and store.history[-1]["content"] == "Fine, fine.")
            assert eval ("[mood: joy]" in tt_test.system_prompt())
            $ persistent.mood_mode = "keywords"

        testcase swipes:
            $ tt_test.mock(reply="Swipe A.")
            type "Say something."
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            $ tt_test.mock(reply="Swipe B.")
            click "Regenerate" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            $ tt_test.mock(reply="Swipe C.")
            click id "swipe_next" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.history[-1]["swipes"] == ["Swipe A.", "Swipe B.", "Swipe C."])
            assert eval (store.swipe_info() == (2, 3))
            # Regenerating must not send the swipe being replaced (B was replaced by C).
            assert eval ("Swipe B." not in json.dumps(tt_test.last_request()["messages"]))
            assert eval (tt_test.last_request()["messages"][-1]["role"] == "user")
            click id "swipe_prev" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.history[-1]["content"] == "Swipe B." and store.swipe_info() == (1, 3))
            screenshot "swipe_1.png"
            $ tt_test.mock(reply="Next turn.")
            type "And then?"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval ("Swipe B." in json.dumps(tt_test.last_request()["messages"]))
            assert eval ("Swipe A." not in json.dumps(tt_test.last_request()["messages"]) and "Swipe C." not in json.dumps(tt_test.last_request()["messages"]))

        testcase chat_log:
            $ tt_test.mock(reply="First answer.")
            type "One"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            $ tt_test.mock(reply="Second answer.")
            type "Two"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            $ tt_test.mock(reply="Third answer.")
            type "Three"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            click id "open_log" until screen "chat_log" timeout 10.0
            assert eval (len(store.log_entries()) == len(store.history) == 7)
            assert eval ([e[1] for e in store.log_entries()][-4:] == ["Two", "Second answer.", "Three", "Third answer."])
            assert eval (store.log_entries()[-1][1] == "Third answer." and store.log_entries()[-2][1] == "Three")
            pause 0.3
            screenshot "log_1.png"
            keysym "K_ESCAPE"
            assert screen "chat_input" timeout 5.0
            assert eval (not renpy.get_screen("chat_log"))

        testcase persistence:
            $ tt_test.mock(reply="Remember this.")
            type "Keep this chat."
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (os.path.exists(store.chat_file))
            $ tt_test.saved_file = store.chat_file
            click "Leave" until not screen "chat_input" timeout 10.0
            pause until screen "card_picker" timeout 10.0
            click id "card_Mira" until not screen "card_picker" timeout 10.0
            advance until screen "choice" timeout 20.0
            click "Continue last chat" until not screen "choice" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (len(store.history) == 3 and store.history[-1]["content"] == "Remember this.")
            assert eval (store.chat_file == tt_test.saved_file)
            # A new chat starts fresh in a new file.
            click "Leave" until not screen "chat_input" timeout 10.0
            pause until screen "card_picker" timeout 10.0
            click id "card_Mira" until not screen "card_picker" timeout 10.0
            advance until screen "choice" timeout 20.0
            click "New chat" until not screen "choice" timeout 10.0
            advance until screen "choice" timeout 20.0
            click "Greeting 1" until not screen "choice" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (len(store.history) == 1 and store.chat_file != tt_test.saved_file)

        testcase persona:
            $ persistent.persona = "A wandering bard with a battered lute."
            type "Hello again."
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval ("Sam's persona: A wandering bard with a battered lute." in tt_test.system_prompt())
            $ persistent.persona = ""

        testcase save_size:
            $ tt_test.big = tt_test.make_big_png()
            assert eval (os.path.getsize(tt_test.big) > 1000000)
            $ renpy.show("char", what=portrait(tt_test.big, expression=None), at_list=[portrait_still])
            pause 0.5
            run FileSave(2, confirm=False)
            pause 0.5
            assert eval (0 < tt_test.save_size(2) < 100 * 1024)
            # The card library must not be kept in the store (it would go into every save).
            assert eval (store.found is None and store.choice is None)

        testcase retry_after_failed_regenerate:
            $ tt_test.mock(reply="First.")
            type "Hi"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            $ tt_test.mock(status=500)
            click "Regenerate" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            $ tt_test.mock(status=200, reply="Second.")
            click "Retry" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.history[-1]["swipes"] == ["First.", "Second."])
            assert eval (store.history[-2]["role"] == "user" and len(store.history) == 3)

        testcase load_older_save_branches_chat:
            $ tt_test.mock(reply="Answer one.")
            type "One"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            run FileSave(3, confirm=False)
            $ tt_test.mock(reply="Answer two.")
            type "Two"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            # Kept on a module: loading a save rewinds store variables.
            $ chatlog._test_newer = store.chat_file
            assert eval (tt_test.chat_len(chatlog._test_newer) == 5)
            run FileLoad(3, confirm=False)
            advance until screen "chat_input" timeout 20.0
            assert eval (store.chat_file != chatlog._test_newer)
            assert eval (tt_test.chat_len(chatlog._test_newer) == 5)
            assert eval (tt_test.chat_len(store.chat_file) == 3)

        testcase percent_sign:
            $ tt_test.mock(reply="I'm 100% sure! Only 5%.")
            type "Sure?"
            click "Send" until not screen "chat_input" timeout 10.0
            advance until screen "chat_input" timeout 20.0
            assert eval (store.history[-1]["content"] == "I'm 100% sure! Only 5%.")

