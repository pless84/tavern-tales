## Styles ------------------------------------------------------------------

define ACCENT = "#ff7eb6"
define PANEL = "#1b1530e6"

style default:
    font "DejaVuSans.ttf"
    size 22
    color "#f2eefc"

style tt_button:
    padding (18, 8)
    background Frame(Solid("#2e2550"), 4, 4)
    hover_background Frame(Solid(ACCENT), 4, 4)
    insensitive_background Frame(Solid("#2e255080"), 4, 4)
style tt_button_text:
    size 20
    color "#f2eefc"
    hover_color "#1b1530"
    selected_color ACCENT
    selected_hover_color "#1b1530"
    insensitive_color "#f2eefc66"

style tt_small_button is tt_button:
    padding (12, 7)
style tt_small_button_text is tt_button_text:
    size 18

style tt_title:
    size 44
    bold True
    color "#ffffff"
    outlines [(3, "#1b1530", 0, 0)]

style tt_bar:
    ysize 18
    left_bar Frame(Solid(ACCENT), 2, 2)
    right_bar Frame(Solid("#2e2550"), 2, 2)
    thumb Solid("#ffffff", xsize=6)
    thumb_offset 3
    xsize 400

style tt_slider is tt_bar

style tt_vscrollbar:
    xsize 10
    unscrollable "hide"
    base_bar Frame(Solid("#2e2550"), 2, 2)
    thumb Frame(Solid(ACCENT), 2, 2)

style tt_label:
    size 18
    color "#b9aedc"

## Say / input / choice --------------------------------------------------

screen say(who, what):
    window id "window":
        style "say_window"
        if who is not None:
            window:
                style "say_namebox"
                text who id "who" style "say_name"
        text what id "what" style "say_text"

style say_window:
    xfill True
    yalign 1.0
    ysize 220
    background Frame(Solid(PANEL), 0, 0)
    padding (220, 62, 220, 20)
style say_namebox:
    pos (-20, -50)
    padding (18, 6)
    background Frame(Solid(ACCENT), 4, 4)
style say_name:
    size 24
    bold True
    color "#1b1530"
style say_text:
    size 24
    line_spacing 4
    xmaximum 840

screen input(prompt):
    style_prefix "tt"
    window:
        style "say_window"
        vbox:
            spacing 14
            text prompt
            input id "input" color ACCENT

screen choice(items):
    vbox:
        xalign 0.5
        yalign 0.4
        spacing 10
        for i in items:
            textbutton i.caption action i.action style "tt_button" text_style "tt_button_text" xminimum 700

## Main menu --------------------------------------------------------------

screen main_menu():
    tag menu
    add "bg tavern"
    vbox:
        xalign 0.5 yalign 0.42
        spacing 14
        text "Tavern Tales" style "tt_title" xalign 0.5
        text "a visual novel for your SillyTavern characters" style "tt_label" xalign 0.5
        null height 24
        style_prefix "tt"
        textbutton "Start" action Start() xalign 0.5 xminimum 280
        textbutton "Load" action ShowMenu("load") xalign 0.5 xminimum 280
        textbutton "AI Settings" action Start("main_menu_settings") xalign 0.5 xminimum 280
        textbutton "Preferences" action ShowMenu("preferences") xalign 0.5 xminimum 280
        textbutton "Characters Folder" action Function(open_folder, cards_dir()) xalign 0.5 xminimum 280
        textbutton "Quit" action Quit(confirm=False) xalign 0.5 xminimum 280

## Character picker -------------------------------------------------------

screen card_picker(cards, errors):
    modal True
    add Solid("#0d0a18cc")
    style_prefix "tt"

    vbox:
        xalign 0.5
        ypos 24
        spacing 12
        xsize 1220

        hbox:
            spacing 12
            text "Choose a character" style "tt_title" size 34
            null width 40
            textbutton "Rescan" action Return("rescan") yalign 0.5
            textbutton "Open folder" action Function(open_folder, cards_dir()) yalign 0.5
            textbutton "AI Settings" action Return("settings") yalign 0.5
            textbutton "Main Menu" action Return("menu") yalign 0.5

        if not cards:
            frame:
                background Frame(Solid(PANEL), 4, 4)
                padding (24, 20)
                xfill True
                vbox:
                    spacing 8
                    text "No characters found."
                    text "Drop SillyTavern character cards (.png or .json) into:" style "tt_label"
                    text escape_renpy(cards_dir()) color ACCENT size 18
                    text "…then press Rescan. A local SillyTavern install is detected automatically." style "tt_label"

        if cards:
            vpgrid:
                cols 6
                spacing 12
                xsize 1220
                ysize 560
                mousewheel True
                scrollbars "vertical"
                allow_underfull True
                if True:
                    for c in cards:
                        button:
                            id "card_" + c["name"]
                            xsize 186 ysize 290
                            background Frame(Solid("#2e2550"), 4, 4)
                            hover_background Frame(Solid(ACCENT), 4, 4)
                            action Return(c)
                            vbox:
                                spacing 6
                                xalign 0.5
                                add portrait(c["avatar"], 166, 230) xalign 0.5
                                text escape_renpy(c["name"]) size 18 xalign 0.5 text_align 0.5 xmaximum 176

        if errors:
            text "Skipped %d file(s): %s" % (len(errors), escape_renpy("; ".join("%s (%s)" % (os.path.basename(p), m) for p, m in errors[:3]))) style "tt_label" size 15

## Chat bar ---------------------------------------------------------------

screen chat_input():
    default msg = ""
    style_prefix "tt"
    key "K_ESCAPE" action ShowMenu("save")
    key "mousedown_4" action Return("log")

    frame:
        xfill True
        yalign 1.0
        ysize 150
        background Frame(Solid(PANEL), 0, 0)
        padding (40, 18)
        vbox:
            spacing 12
            hbox:
                spacing 10
                text escape_renpy(persistent.user_name) + ":" color "#9fd8ff" yalign 0.5
                frame:
                    xsize 900
                    background Frame(Solid("#0d0a18"), 4, 4)
                    padding (12, 8)
                    input value ScreenVariableInputValue("msg", returnable=True) length 1000 color "#ffffff" pixel_width 870
                textbutton "Send" action Return(msg) yalign 0.5
            hbox:
                spacing 8
                style_prefix "tt_small"
                textbutton "Regenerate" action Return("regenerate")
                textbutton "Retry" action Return("retry")
                $ sw = swipe_info()
                if sw:
                    textbutton "‹" id "swipe_prev" action Return("swipe_prev") sensitive sw[0] > 0
                    text "%d/%d" % (sw[0] + 1, sw[1]) yalign 0.5 size 18 color "#b9aedc"
                    textbutton "›" id "swipe_next" action Return("swipe_next")
                textbutton "Log" id "open_log" action Return("log")
                textbutton "Save" action ShowMenu("save")
                textbutton "Load" action ShowMenu("load")
                textbutton "Prefs" action ShowMenu("preferences")
                textbutton "AI Settings" action Return("settings")
                textbutton "Leave" action Return("leave")

screen chat_log():
    modal True
    zorder 60
    style_prefix "tt"
    key "K_ESCAPE" action Return()
    key "game_menu" action Return()
    add Solid("#0d0a18f2")
    vbox:
        xalign 0.5 ypos 24
        spacing 12
        xsize 1180
        hbox:
            spacing 20
            text "Chat log" style "tt_title" size 34
            textbutton "Close" id "close_log" action Return() yalign 0.5
        viewport:
            id "log_viewport"
            ysize 610
            mousewheel True
            scrollbars "vertical"
            yinitial 1.0
            vbox:
                spacing 14
                xsize 1150
                for who, line, is_user in log_entries():
                    vbox:
                        spacing 2
                        text who size 18 bold True color ("#9fd8ff" if is_user else ACCENT)
                        text line size 20 xmaximum 1130

screen streaming_reply():
    zorder 40
    style_prefix "tt"
    timer 0.1 repeat True action Function(stream_tick)
    $ status, live = stream_view()
    window:
        style "say_window"
        window:
            style "say_namebox"
            text escape_renpy(card_name) style "say_name"
        if live:
            text live style "say_text"
        else:
            text status style "say_text" italic True color "#b9aedc"
    textbutton "Cancel":
        id "cancel_reply"
        action Return("cancel")
        xalign 0.985 yalign 0.975

## AI settings ------------------------------------------------------------

screen ai_settings_screen(status=""):
    modal True
    default editing = None
    default shown_dirs = card_dirs()
    add Solid("#0d0a18ee")
    style_prefix "tt"

    vbox:
        xalign 0.5 ypos 14
        spacing 8
        xsize 1100
        text "AI Settings" style "tt_title" size 34
        text "Any OpenAI-compatible chat API works. Pick a preset or type your own." style "tt_label"

        hbox:
            spacing 8
            box_wrap True
            for lbl, url in API_PRESETS:
                textbutton lbl action [SetField(persistent, "api_base", url), SetScreenVariable("editing", None)] selected (persistent.api_base == url)

        for fld, lbl, secret in [("api_base", "API URL", False), ("api_key", "API key", True), ("model", "Model", False), ("user_name", "Your name", False), ("persona", "Your persona", False)]:
            hbox:
                spacing 12
                text lbl style "tt_label" xsize 140 yalign 0.5
                button:
                    xsize 900
                    background Frame(Solid("#2e2550" if editing != fld else "#0d0a18"), 4, 4)
                    padding (12, 8)
                    action SetScreenVariable("editing", fld)
                    if editing == fld:
                        input value FieldInputValue(persistent, fld) color "#ffffff" pixel_width 870 multiline (fld == "persona")
                    else:
                        $ v = getattr(persistent, fld) or ""
                        $ v_short = (v[:110] + "…") if len(v) > 110 else v
                        text (("•" * min(len(v), 24)) if (secret and v) else escape_renpy(v_short.replace("\n", " ") or ("(empty — click to edit)" if fld != "persona" else "(optional — describe yourself; Shift+Enter for a new line)"))) color ("#ffffff" if v else "#ffffff66")

        hbox:
            spacing 12
            text "Temperature" style "tt_label" xsize 140 yalign 0.5
            bar value FieldValue(persistent, "temperature", 2.0, step=0.05, offset=0) xsize 400 yalign 0.5
            text "%.2f" % persistent.temperature yalign 0.5
        hbox:
            spacing 12
            text "Max tokens" style "tt_label" xsize 140 yalign 0.5
            bar value FieldValue(persistent, "max_tokens", 1000, step=10, offset=50) xsize 400 yalign 0.5
            text "%d" % persistent.max_tokens yalign 0.5

        hbox:
            spacing 12
            text "Context size" style "tt_label" xsize 140 yalign 0.5
            bar value FieldValue(persistent, "context_tokens", 31744, step=512, offset=1024) xsize 400 yalign 0.5
            text "%d tokens" % persistent.context_tokens yalign 0.5
            textbutton "Auto-detect" action Return("detect") yalign 0.5

        hbox:
            spacing 12
            text "Expressions" style "tt_label" xsize 140 yalign 0.5
            for mode, lbl in [("keywords", "From keywords"), ("model", "Ask the model"), ("off", "Off")]:
                textbutton lbl action SetField(persistent, "mood_mode", mode) selected persistent.mood_mode == mode

        hbox:
            spacing 12
            text "Card folders" style "tt_label" xsize 140
            vbox:
                for d in shown_dirs:
                    text escape_renpy(d) size 16

        null height 6
        hbox:
            spacing 12
            textbutton "Test connection" action Return("test")
            textbutton "Done" action Return("done")
        $ warn = insecure_key_warning()
        if warn:
            text escape_renpy(warn) size 18 color "#ff9a9a"
        if status:
            text escape_renpy(status) size 18 color ACCENT

## Preferences ------------------------------------------------------------

screen preferences():
    tag menu
    modal True
    style_prefix "tt"
    key "K_ESCAPE" action Return()
    add Solid("#0d0a18f2")
    vbox:
        xalign 0.5 ypos 30
        spacing 18
        xsize 1100
        text "Preferences" style "tt_title" size 34

        hbox:
            spacing 12
            text "Text speed" style "tt_label" xsize 200 yalign 0.5
            bar value Preference("text speed") id "text_speed_bar" yalign 0.5
            text ("Instant" if not preferences.text_cps else "%d chars/s" % preferences.text_cps) yalign 0.5
        hbox:
            spacing 12
            text "Auto-forward" style "tt_label" xsize 200 yalign 0.5
            textbutton ("On" if preferences.afm_enable else "Off") id "afm_toggle" action Preference("auto-forward", "toggle") selected preferences.afm_enable
            bar value Preference("auto-forward time") yalign 0.5
        hbox:
            spacing 12
            text "Display" style "tt_label" xsize 200 yalign 0.5
            textbutton "Window" action Preference("display", "window")
            textbutton "Fullscreen" action Preference("display", "fullscreen")
        hbox:
            spacing 12
            text "Dialogue text size" style "tt_label" xsize 200 yalign 0.5
            bar value FieldValue(persistent, "text_size", 16, step=1, offset=18, action=Function(apply_text_size)) id "text_size_bar" yalign 0.5
            text "%d" % persistent.text_size yalign 0.5
        frame:
            background Frame(Solid(PANEL), 4, 4)
            padding (24, 16)
            xfill True
            text "Preview: {i}She smiles.{/i} This is how dialogue will look." size persistent.text_size

        hbox:
            spacing 12
            textbutton "Return" action Return()
            if not main_menu:
                textbutton "Save" action ShowMenu("save")
                textbutton "Load" action ShowMenu("load")

## Save / load / game menu -----------------------------------------------

screen save():
    tag menu
    use file_slots("Save")

screen load():
    tag menu
    use file_slots("Load")

screen file_slots(title):
    modal True
    add Solid("#0d0a18f2")
    style_prefix "tt"
    vbox:
        xalign 0.5 ypos 30
        spacing 16
        text title style "tt_title" size 34
        grid 3 2:
            spacing 16
            for i in range(1, 7):
                button:
                    xsize 360 ysize 250
                    background Frame(Solid("#2e2550"), 4, 4)
                    hover_background Frame(Solid(ACCENT), 4, 4)
                    action (FileSave(i) if title == "Save" else FileLoad(i))
                    vbox:
                        spacing 6
                        add FileScreenshot(i) xalign 0.5 size (320, 180)
                        text (FileTime(i, format="%b %d, %H:%M", empty="Empty slot")) size 18 xalign 0.5
        hbox:
            spacing 12
            textbutton "Return" action Return()
            textbutton "Preferences" action ShowMenu("preferences")
            textbutton "Main Menu" action MainMenu()
            textbutton "Quit" action Quit()

screen confirm(message, yes_action, no_action):
    modal True
    zorder 200
    add Solid("#000a")
    style_prefix "tt"
    frame:
        xalign 0.5 yalign 0.5
        background Frame(Solid(PANEL), 4, 4)
        padding (40, 30)
        vbox:
            spacing 20
            text _(message) xalign 0.5
            hbox:
                xalign 0.5
                spacing 20
                textbutton _("Yes") action yes_action
                textbutton _("No") action no_action

screen notify(message):
    zorder 100
    frame:
        xalign 0.5 ypos 20
        background Frame(Solid(ACCENT), 4, 4)
        padding (20, 8)
        text "[message!tq]" color "#1b1530" size 18
    timer 3.0 action Hide("notify")
