# Tavern Tales

A Ren'Py visual novel that imports SillyTavern character cards and lets you chat
with them VN-style, powered by any OpenAI-compatible LLM backend.

## Run

    ./run.sh               # play (uses ~/Games/renpy-8.5.3-sdk, or $RENPY_SDK)
    bash tools/check.sh    # all tests: unit, lint, Ren'Py test suite (mock AI, no Ollama needed)

(Or open this folder in the Ren'Py SDK launcher.)

## Characters

Drop cards into `characters/`, then press **Rescan** in the picker:

- PNG cards: V1/V2 (`chara` chunk) and V3 (`ccv3` chunk)
- `.json` exports (a same-named `.png` beside it is used as the portrait)
- A local SillyTavern install (`SillyTavern/data/*/characters`) is detected automatically

Used fields: name, description, personality, scenario, first message, alternate
greetings (you pick one), example dialogue, system prompt, post-history
instructions, embedded lorebook (keyword-triggered). `{{char}}`, `{{user}}` and
`{{persona}}` macros are expanded.

**Expression sprites:** put SillyTavern-style sprites in a folder named after the
character, e.g. `characters/Mira/joy.png`, `neutral.png`, `surprise.png` (any of
SillyTavern's 28 labels). The mood of each reply comes from keywords, or from a
`[mood: x]` tag the model adds (AI Settings → Expressions).

## Chatting

- Replies **stream** in as they're written. **Cancel** stops a slow reply.
- **Regenerate** or **›** makes another version (a swipe); **‹ ›** flip between them.
- **Log** (or mouse wheel up) shows the whole conversation.
- Chats are saved automatically to `chats/<card>/` in SillyTavern's `.jsonl`
  format. Picking a character again offers **Continue last chat**, **New chat**,
  or **Import a SillyTavern chat**.
- Ren'Py save slots work as usual on top of that.

## AI backend

**AI Settings** has presets for KoboldCpp, Ollama (default), LM Studio,
text-generation-webui, OpenRouter and OpenAI. Leave **Model** empty to use the
first model the server lists. **Context size** limits how much history is sent
(**Auto-detect** asks Ollama). **Your persona** is sent to the model as a
description of you.

## Layout

- `game/stcards.py`: card parser and expression sprite discovery
- `game/prompting.py`: token budget, prompt fitting, mood detection
- `game/llmstream.py`: streaming HTTP client (background thread, cancellable)
- `game/chatlog.py`: SillyTavern chat files
- `game/chat.rpy`: Ren'Py glue: prompt building, streaming, swipes, portraits
- `game/script.rpy`: game flow (pick → continue/new → greet → chat loop)
- `game/screens.rpy`: all UI
- `game/testcases.rpy`: Ren'Py test suite (run via `tools/check.sh`)
- `tools/`: `check.sh`, `mock_llm.py` (fake AI server for tests), unit tests,
  `make_assets.py` (background + sample cards and sprites)

Tests run on a temporary copy of the project with its own save folder, so they
never touch your saves, settings or cards.
