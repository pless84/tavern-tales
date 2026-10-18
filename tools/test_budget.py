"""Tests for game/prompting.py. Usage: python3 tools/test_budget.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "game"))
import prompting as P  # noqa: E402


def test_trim():
    history = [{"role": "user" if i % 2 else "assistant", "content": ("m%03d " % i) + "x" * 395}
               for i in range(200)]
    system_tokens = 0
    budget = P.history_budget(4096, 350, system_tokens)
    kept = P.trim_history(history, budget)
    total = sum(P.estimate_tokens(m["content"]) for m in kept)
    assert total <= 3746, total
    assert kept[-1] is history[-1], "newest message must be kept"
    idx = [history.index(m) for m in kept]
    assert idx == sorted(idx) and idx == list(range(idx[0], 200)), "order / contiguity"
    assert len(kept) < 200


def test_trim_keeps_newest_even_if_huge():
    h = [{"role": "user", "content": "a"}, {"role": "user", "content": "b" * 100000}]
    kept = P.trim_history(h, 10)
    assert kept == [h[-1]]


def test_fit_system():
    parts = [("core", "c" * 700), ("example", "e" * 7000), ("lore", "l" * 3500)]
    fitted = P.fit_system(parts, budget=600)
    assert sum(P.estimate_tokens(t) for _, t in fitted) <= 600, fitted
    assert fitted[0] == parts[0], "core part must never shrink"


def test_mood():
    samples = [
        ("*She laughs brightly* That's wonderful!", "joy"),
        ("*He glares at you, furious.* Get out.", "anger"),
        ("*She sniffles, tears in her eyes.*", "sadness"),
        ("*Her eyes go wide and she gasps.* No way!", "surprise"),
        ("*She blushes and looks away, flustered.*", "embarrassment"),
        ("*He trembles, clearly terrified.*", "fear"),
        ("The weather is mild today.", "neutral"),
        ("*She chuckles and smirks.* Very funny.", "amusement"),
        ("*He sighs, annoyed.* Ugh, again?", "annoyance"),
        ("*She tilts her head, curious.* Hmm, interesting.", "curiosity"),
    ]
    right = sum(P.classify_mood(t) == want for t, want in samples)
    assert right >= 8, [(t, P.classify_mood(t), w) for t, w in samples]


def test_mood_tag():
    text, label = P.extract_mood_tag("Hello there! [mood: joy]")
    assert text == "Hello there!" and label == "joy"
    text, label = P.extract_mood_tag("No tag here.")
    assert label is None and text == "No tag here."
    text, label = P.extract_mood_tag("Odd [mood: banana]")
    assert label is None and text == "Odd"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("all budget/mood tests passed")
