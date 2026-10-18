"""Tests for game/llmstream.py against tools/mock_llm.py. Usage: python3 tools/test_stream.py"""
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "game"))
import llmstream  # noqa: E402

PORT = int(os.environ.get("TT_UNIT_MOCK_PORT", 8798))
BASE = "http://127.0.0.1:%d" % PORT
URL = BASE + "/v1/chat/completions"
PAYLOAD = {"messages": [{"role": "user", "content": "hi"}]}


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def mock_log():
    return json.loads(urllib.request.urlopen(BASE + "/_log", timeout=5).read())


def wait_done(s, limit=10):
    end = time.time() + limit
    while not s.done and time.time() < end:
        time.sleep(0.02)
    assert s.done, "stream did not finish"


def test_stream_basic():
    reply = "*She waves.* " + "word " * 40
    post("/_reset", {})
    post("/_config", {"reply": reply, "chunk_delay": 0.03})
    s = llmstream.start(URL, PAYLOAD)
    seen_partial = False
    end = time.time() + 10
    while not s.done and time.time() < end:
        t = s.snapshot()
        if 0 < len(t) < len(reply):
            seen_partial = True
        time.sleep(0.01)
    wait_done(s)
    assert seen_partial, "never saw partial text"
    assert s.error is None, s.error
    assert s.text == reply
    assert mock_log()[-1]["request"]["stream"] is True


def test_cancel_during_delay():
    post("/_reset", {})
    post("/_config", {"delay": 30})
    s = llmstream.start(URL, PAYLOAD)
    time.sleep(0.5)
    t0 = time.time()
    s.cancel()
    wait_done(s, 3)
    assert time.time() - t0 < 1.0
    assert s.error is None and s.text == ""
    time.sleep(0.3)
    assert mock_log()[-1]["disconnected"] is True, mock_log()


def test_cancel_mid_stream():
    post("/_reset", {})
    post("/_config", {"reply": "x" * 400, "chunk_delay": 0.2})
    s = llmstream.start(URL, PAYLOAD)
    end = time.time() + 5
    while not s.snapshot() and time.time() < end:
        time.sleep(0.02)
    s.cancel()
    wait_done(s, 3)
    assert 0 < len(s.text) < 400


def test_cancel_immediately():
    post("/_reset", {})
    post("/_config", {"delay": 30})
    s = llmstream.start(URL, PAYLOAD)
    s.cancel()
    wait_done(s, 2)
    assert s.error is None and s.text == ""


def test_connect_timeout_is_short():
    # 10.255.255.1 is unroutable: connect should give up after connect_timeout, not 600 s.
    t0 = time.time()
    s = llmstream.ReplyStream("http://10.255.255.1:9/v1/chat/completions", PAYLOAD, connect_timeout=1)
    wait_done(s, 5)
    assert time.time() - t0 < 4 and s.error, s.error


def test_non_stream_fallback():
    post("/_reset", {})
    post("/_config", {"stream_mode": "never", "reply": "Plain reply."})
    s = llmstream.start(URL, PAYLOAD)
    wait_done(s)
    assert s.error is None and s.text == "Plain reply."


def test_http_error():
    post("/_reset", {})
    post("/_config", {"status": 500})
    s = llmstream.start(URL, PAYLOAD)
    wait_done(s)
    assert s.error and "500" in s.error and "mock failure" in s.error, s.error


def test_connection_refused():
    s = llmstream.start("http://127.0.0.1:1/v1/chat/completions", PAYLOAD)
    wait_done(s)
    assert s.error and "refused" in s.error.lower(), s.error


def test_get_by_id():
    post("/_reset", {})
    s = llmstream.start(URL, PAYLOAD)
    assert llmstream.get(s.id) is s
    assert llmstream.get("nope") is None
    wait_done(s)


if __name__ == "__main__":
    mock = subprocess.Popen([sys.executable, os.path.join(ROOT, "tools", "mock_llm.py"), str(PORT)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(BASE + "/v1/models", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                fn()
        print("all stream tests passed")
    finally:
        mock.terminate()
