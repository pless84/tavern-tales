"""Prompt budgeting and mood detection (pure Python, no Ren'Py imports)."""

import math
import re

CHARS_PER_TOKEN = 3.5
MESSAGE_OVERHEAD = 4

# SillyTavern's expression labels (the "classify" set).
EXPRESSIONS = (
    "admiration", "amusement", "anger", "annoyance", "approval", "caring", "confusion",
    "curiosity", "desire", "disappointment", "disapproval", "disgust", "embarrassment",
    "excitement", "fear", "gratitude", "grief", "joy", "love", "nervousness", "neutral",
    "optimism", "pride", "realization", "relief", "remorse", "sadness", "surprise",
)


# ---- Token budget ----------------------------------------------------------

def estimate_tokens(text):
    return int(math.ceil(len(text or "") / CHARS_PER_TOKEN)) + MESSAGE_OVERHEAD


def history_budget(context_tokens, max_tokens, system_tokens):
    return max(0, int(context_tokens) - int(max_tokens) - int(system_tokens))


def trim_history(history, budget):
    """Newest-first selection of messages that fit `budget` tokens, returned in order.

    The newest message is always kept, even if it alone exceeds the budget.
    """
    kept, used = [], 0
    for msg in reversed(history):
        cost = estimate_tokens(msg["content"])
        if kept and used + cost > budget:
            break
        kept.append(msg)
        used += cost
    kept.reverse()
    return kept


def fit_system(parts, budget, shrinkable=("example", "lore")):
    """Shrink optional system-prompt parts until their total fits `budget`.

    `parts` is a list of (kind, text). Parts whose kind is in `shrinkable` are
    truncated (in that order) and dropped if needed. Returns the new list.
    """
    parts = list(parts)

    def total():
        return sum(estimate_tokens(t) for _, t in parts)

    for kind in shrinkable:
        for i, (k, t) in enumerate(parts):
            if k != kind or total() <= budget:
                continue
            over = total() - budget
            keep_chars = max(0, len(t) - int(over * CHARS_PER_TOKEN) - 16)
            parts[i] = (k, t[:keep_chars].rstrip() + "…") if keep_chars > 40 else (k, "")
        parts = [(k, t) for k, t in parts if t]
    return parts


# ---- Mood ------------------------------------------------------------------

_LEXICON = {
    "joy": "laugh laughs laughing laughed giggle giggles grin grins grinning beam beams beaming happy happily glad delighted wonderful yay smile smiles smiling cheerful brightly",
    "amusement": "chuckle chuckles chuckling smirk smirks funny amused snicker teasing teases",
    "anger": "angry furious rage glare glares glaring snarl snarls shout shouts yell yells clench clenches seething",
    "annoyance": "annoyed sigh sighs huff huffs eye-roll rolls irritated ugh scowl scowls",
    "sadness": "sad cry cries crying tear tears sob sobs sniffle sniffles frown frowns lonely gloomy",
    "grief": "grief mourn mourns devastated heartbroken",
    "fear": "afraid scared fear terrified tremble trembles shiver shivers panic panics flinch flinches",
    "nervousness": "nervous fidget fidgets stammer stammers anxious bites hesitates hesitant",
    "surprise": "surprised gasp gasps startled wide-eyed blink blinks whoa wow shocked",
    "embarrassment": "blush blushes blushing flustered embarrassed sheepish sheepishly",
    "love": "love adore darling sweetheart cherish hug hugs kiss kisses",
    "curiosity": "curious tilts wonder wonders intrigued hmm interested",
    "confusion": "confused puzzled frowning baffled huh",
    "caring": "gently softly comfort comforts reassuring reassures care cares worried",
    "gratitude": "thank thanks grateful appreciate",
    "excitement": "excited thrilled can't-wait bouncing eagerly eager",
    "disgust": "disgust disgusted gross grimace grimaces yuck",
    "pride": "proud proudly smug",
    "relief": "relieved relief phew exhale exhales",
}
_WORDS = {label: set(words.split()) for label, words in _LEXICON.items()}


def classify_mood(text):
    """Pick an expression label from keywords. Ties and no hits give 'neutral'."""
    words = re.findall(r"[a-z'-]+", (text or "").lower().replace("\u2019", "'"))
    scores = {}
    for w in words:
        for label, vocab in _WORDS.items():
            if w in vocab:
                scores[label] = scores.get(label, 0) + 1
    if not scores:
        return "neutral"
    best = max(scores.values())
    top = [l for l, s in scores.items() if s == best]
    return top[0] if len(top) == 1 else "neutral"


_TAG = re.compile(r"\[\s*mood\s*:\s*([a-z]+)\s*\]", re.I)

MOOD_INSTRUCTION = ("At the very end of every reply, add a mood tag for {{char}}'s current expression, "
                    "exactly like [mood: joy], using one of: " + ", ".join(EXPRESSIONS) + ".")


def extract_mood_tag(text):
    """Remove every [mood: x] tag. Returns (clean_text, label or None)."""
    label = None
    for m in _TAG.finditer(text or ""):
        cand = m.group(1).lower()
        if cand in EXPRESSIONS:
            label = cand
    return _TAG.sub("", text or "").strip(), label
