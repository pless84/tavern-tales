"""Streaming OpenAI-compatible chat client (stdlib only, no Ren'Py imports).

A ReplyStream runs the request on a background thread and exposes the text
received so far. Cancel closes the socket, so the server stops generating.
Stream objects must never be stored in Ren'Py's store (they hold a thread and
a socket); keep them on this module via CURRENT.
"""

import http.client
import itertools
import json
import socket
import ssl
import threading
import time
import urllib.parse

CURRENT = None          # the active ReplyStream, if any
_ids = itertools.count(1)


class ReplyStream(object):

    def __init__(self, url, payload, headers=None, timeout=600, connect_timeout=10):
        self.id = "%d-%d" % (int(time.time() * 1000), next(_ids))
        self.url = url
        self.payload = dict(payload, stream=True)
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.connect_timeout = connect_timeout

        self.text = ""
        self.error = None
        self.done = False
        self.cancelled = False
        self.started_at = time.time()
        self.first_token_at = None

        self._lock = threading.Lock()
        self._conn = None
        self._thread = threading.Thread(target=self._run, name="ReplyStream")
        self._thread.daemon = True
        self._thread.start()

    # -- public ----------------------------------------------------------

    def snapshot(self):
        with self._lock:
            return self.text

    def elapsed(self):
        return time.time() - self.started_at

    def cancel(self):
        with self._lock:
            self.cancelled = True
            conn = self._conn
        if conn is not None:
            try:
                if conn.sock is not None:
                    conn.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except Exception:
                pass

    # -- worker ----------------------------------------------------------

    def _append(self, piece):
        if not piece:
            return
        with self._lock:
            if self.first_token_at is None:
                self.first_token_at = time.time()
            self.text += piece

    def _run(self):
        try:
            self._request()
        except Exception as e:
            if not self.cancelled:
                self.error = _describe(e)
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self.done = True

    def _request(self):
        u = urllib.parse.urlsplit(self.url)
        port = u.port or (443 if u.scheme == "https" else 80)
        if u.scheme == "https":
            conn = http.client.HTTPSConnection(u.hostname, port, timeout=self.connect_timeout,
                                               context=ssl.create_default_context())
        else:
            conn = http.client.HTTPConnection(u.hostname, port, timeout=self.connect_timeout)
        conn.connect()
        with self._lock:
            if self.cancelled:
                conn.close()
                return
            self._conn = conn
        # Connected: now allow a long wait for the first token (CPU models can take minutes).
        conn.sock.settimeout(self.timeout)

        path = u.path + ("?" + u.query if u.query else "")
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        headers.update(self.headers)
        conn.request("POST", path, body=json.dumps(self.payload).encode("utf-8"), headers=headers)
        resp = conn.getresponse()

        if resp.status >= 400:
            body = resp.read(2000).decode("utf-8", "replace")
            raise RuntimeError("HTTP %d: %s" % (resp.status, _error_message(body)))

        ctype = (resp.getheader("Content-Type") or "").lower()
        if "event-stream" not in ctype:
            # Server ignored "stream": parse a normal JSON reply.
            data = json.loads(resp.read().decode("utf-8"))
            self._append(_content(data, delta=False))
            return

        while not self.cancelled:
            raw = resp.readline()
            if not raw:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line or line.startswith(":") or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("error"):
                raise RuntimeError(_error_message(json.dumps(obj)))
            self._append(_content(obj, delta=True))
        conn.close()


def _content(obj, delta):
    try:
        choice = obj["choices"][0]
    except (KeyError, IndexError, TypeError):
        return ""
    part = choice.get("delta" if delta else "message") or {}
    text = part.get("content")
    if text is None and delta:
        text = (choice.get("message") or {}).get("content") or choice.get("text")
    return text or ""


def _error_message(body):
    try:
        obj = json.loads(body)
        err = obj.get("error", obj)
        if isinstance(err, dict):
            return err.get("message") or json.dumps(err)[:300]
        return str(err)[:300]
    except ValueError:
        return body[:300]


def _describe(e):
    msg = str(e) or type(e).__name__
    if isinstance(e, (socket.timeout, TimeoutError)) or "timed out" in msg.lower():
        return "The request timed out. Local models can be slow; try a smaller model or lower Max tokens."
    if isinstance(e, ConnectionRefusedError):
        return "Connection refused. Is the AI server running? (%s)" % msg
    return msg


def parse_models(data):
    """Model ids from an OpenAI-style /models reply, in server order."""
    entries = data.get("data", []) if isinstance(data, dict) else []
    return [m["id"] for m in entries if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"]]


class ModelList(object):
    """Fetches /models on a background thread. Check .done, then .ids or .error."""

    def __init__(self, url, headers=None, timeout=15):
        self.url = url
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.ids = []
        self.error = None
        self.done = False
        t = threading.Thread(target=self._run, name="ModelList")
        t.daemon = True
        t.start()

    def _run(self):
        import urllib.request
        try:
            req = urllib.request.Request(self.url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                self.ids = parse_models(json.loads(r.read(4 * 1024 * 1024).decode("utf-8")))
        except Exception as e:
            self.error = _describe(e)
        finally:
            self.done = True


MODELS = None           # the latest ModelList, if any


def list_models(url, headers=None, timeout=15):
    global MODELS
    MODELS = ModelList(url, headers, timeout)
    return MODELS


def start(url, payload, headers=None, timeout=600):
    """Cancel any running stream and start a new one."""
    global CURRENT
    if CURRENT is not None and not CURRENT.done:
        CURRENT.cancel()
    CURRENT = ReplyStream(url, payload, headers, timeout)
    return CURRENT


def get(stream_id):
    """The current stream if it matches stream_id, else None (e.g. after loading a save)."""
    if CURRENT is not None and CURRENT.id == stream_id:
        return CURRENT
    return None
