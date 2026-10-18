define narrator = Character(None, what_italic=True, what_color="#d9d2f0")
define bot = Character("[card_name!q]")
define you = Character("[persistent.user_name!q]")

image bg tavern = "images/bg_tavern.png"

init 1 python:
    style.say_text.size = int(persistent.text_size or 24)

transform portrait_still:
    xalign 0.5 yalign 1.0 alpha 1.0

transform portrait_pos:
    xalign 0.5 yalign 1.0
    alpha 0.0
    easein 0.4 alpha 1.0

label start:
    if not persistent.user_name:
        $ persistent.user_name = renpy.input("What's your name?", length=24).strip() or "Traveler"
    jump pick_character

label pick_character:
    scene bg tavern
    $ found, scan_errors = scan_cards()
    $ choice = renpy.call_screen("card_picker", cards=found, errors=scan_errors)

    if choice == "settings":
        call ai_settings
        jump pick_character
    elif choice == "rescan":
        jump pick_character
    elif choice == "menu":
        $ renpy.full_restart()

    $ card = choice
    $ found = scan_errors = choice = None   # don't pickle the whole card library into saves
    $ card_name = card["name"]
    $ history = []
    $ load_expressions()

    # Continue, start fresh, or import a SillyTavern chat.
    $ existing = chatlog.list_chats(chat_dir())
    $ st_files = st_chat_files()
    if existing or st_files:
        python:
            items = []
            if existing:
                items.append(("Continue last chat", "continue"))
            items.append(("New chat", "new"))
            if st_files:
                items.append(("Import a SillyTavern chat", "import"))
            how = renpy.display_menu(items)
        if how == "continue":
            $ open_chat(existing[0])
            $ existing = st_files = items = None
            jump resume
        if how == "import":
            $ src = renpy.display_menu([(escape_renpy(os.path.basename(f)), f) for f in st_files[:12]])
            $ open_chat(src, copy=True)
            $ existing = st_files = items = src = None
            jump resume
    $ existing = st_files = items = None
    $ new_chat()
    jump meet

label resume:
    scene bg tavern
    python:
        last = history[-1] if history else None
        current_expression, current_sprite = sprite_for(last.get("mood") if last and last["role"] == "assistant" else "neutral")
    show expression portrait(current_sprite, expression=current_expression) as char at portrait_pos
    with dissolve
    if last and last["role"] == "assistant":
        $ say_reply(last["content"], last.get("mood"))
    jump chat_loop

label meet:
    scene bg tavern
    $ current_expression, current_sprite = sprite_for("neutral")
    show expression portrait(current_sprite, expression=current_expression) as char at portrait_pos
    with dissolve

    if card["scenario"]:
        $ renpy.say(narrator, escape_renpy(macros(card["scenario"])))

    python:
        greetings = [g for g in [card["first_mes"]] + card["alternate_greetings"] if g.strip()]
        if len(greetings) > 1:
            items = [(("Greeting %d: " % (i + 1)) + escape_renpy(macros(g)[:80].replace("\n", " ")) + "…", g)
                     for i, g in enumerate(greetings)]
            greeting = renpy.display_menu(items)
        elif greetings:
            greeting = greetings[0]
        else:
            greeting = ""
        greeting = macros(greeting)
        if greeting:
            add_reply(greeting, prompting.classify_mood(greeting))
            say_reply(greeting, history[-1]["mood"])
        renpy.block_rollback()
    jump chat_loop

label chat_loop:
    $ save_chat()
    $ action = renpy.call_screen("chat_input")

    if action == "leave":
        hide char with dissolve
        jump pick_character
    elif action == "settings":
        call ai_settings
    elif action == "regenerate":
        if history and history[-1]["role"] == "assistant" and len(history) > 1:
            call reply(reply_swipe=True)
        else:
            $ renpy.notify("Nothing to regenerate yet.")
    elif action == "log":
        call screen chat_log
    elif action == "swipe_prev":
        $ switch_swipe(-1)
        $ say_reply(history[-1]["content"], history[-1].get("mood"))
    elif action == "swipe_next":
        if swipe_info() and swipe_info()[0] < swipe_info()[1] - 1:
            $ switch_swipe(1)
            $ say_reply(history[-1]["content"], history[-1].get("mood"))
        else:
            call reply(reply_swipe=True)
    elif action == "retry":
        # Answer a pending user message; otherwise redo the last reply as a new swipe.
        if history and history[-1]["role"] == "user":
            call reply
        elif len(history) > 1:
            call reply(reply_swipe=True)
        else:
            $ renpy.notify("Nothing to retry.")
    elif isinstance(action, str) and action.strip():
        $ history.append({"role": "user", "content": action.strip(), "send_date": chatlog.send_date()})
        call reply
    jump chat_loop

label reply(reply_swipe=False):
    # reply_swipe: regenerate the last assistant message as a new swipe.
    $ reply_text = reply_error = reply_mood = None
    label .request:
        $ start_reply(exclude_last=reply_swipe)
        $ reply_outcome = None
        $ reply_outcome = renpy.call_screen("streaming_reply")
    if reply_outcome == "lost":
        jump .request
    if reply_outcome == "cancel":
        $ cancel_reply()
        $ renpy.notify("Reply cancelled.")
        return
    $ reply_text, reply_error, reply_mood = finish_reply()
    # Nothing to read means we resumed from a save made while waiting: ask again.
    if reply_text is None and reply_error is None:
        jump .request
    if reply_error:
        $ renpy.say(narrator, "{color=#ff9a9a}Couldn't get a reply:{/color} " + escape_renpy(reply_error[:300]) + "\n\nCheck {b}AI Settings{/b}, then press {b}Retry{/b}.")
        return
    $ add_reply(reply_text, reply_mood, as_swipe=reply_swipe)
    $ say_reply(reply_text, reply_mood)
    return

label ai_settings:
    $ settings_status = ""
    label .loop:
        $ r = renpy.call_screen("ai_settings_screen", status=settings_status)
        if r == "test":
            $ settings_status = "Testing…"
            $ settings_status = test_connection()
            jump .loop
        if r == "models":
            $ start_model_list()
            $ picked = renpy.call_screen("model_picker")
            if isinstance(picked, basestring) and picked:
                $ persistent.model = picked
                $ settings_status = "Model set to %s." % picked
            jump .loop
        if r == "detect":
            $ settings_status = detect_context()
            jump .loop
    return

# Opened from the main menu.
label main_menu_settings:
    call ai_settings
    return
