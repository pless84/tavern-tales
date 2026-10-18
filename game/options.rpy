define config.name = "Tavern Tales"
define config.version = "0.2.0"
define build.name = "TavernTales"
define config.save_directory = "TavernTales-1761000000"

define config.screen_width = 1280
define config.screen_height = 720

# Chat replies come from the network, so rolling back can't replay them.
define config.rollback_enabled = False

default preferences.text_cps = 60
define config.window_title = "Tavern Tales"

# Card text is untrusted: never evaluate Python expressions inside [brackets].
define config.interpolate_exprs = False

# Model replies often contain "%" (e.g. "100% sure"); don't treat it as old-style formatting.
define config.old_substitutions = False

init python:
    # Never ship test files or local saves in a distribution build.
    build.classify("game/testcases.rpy*", None)
    build.classify("game/saves/**", None)
    build.classify("chats/**", None)
    build.classify("tests/**", None)
    build.classify("tools/**", None)
