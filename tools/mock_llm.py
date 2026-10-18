"""A tiny OpenAI-compatible mock server for tests (stdlib only).

Usage: python3 tools/mock_llm.py [port]   (default 8799)

Endpoints:
  GET  /v1/models
  POST /v1/chat/completions      honours "stream": true (SSE)
  POST /_config                  JSON body updates the knobs below
  GET  /_log                     JSON list of requests received (+ "disconnected" flags)
  POST /_reset                   reset knobs and log

Knobs (also settable via env MOCK_*):
  delay        seconds before the first byte
  chunk_delay  seconds between streamed chunks
  reply        reply text (streamed in ~20 chunks)
  status       HTTP status to return (e.g. 500)
  stream_mode  "auto" (follow the request) or "never" (always reply non-streamed)
"""
import json
import os
import select
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULTS = {
    "delay": float(os.environ.get("MOCK_DELAY", 0)),
    "chunk_delay": float(os.environ.get("MOCK_CHUNK_DELAY", 0.02)),
    "reply": os.environ.get("MOCK_REPLY", "*She smiles warmly.* Hello there! It's good to see you."),
    "status": int(os.environ.get("MOCK_STATUS", 200)),
    "stream_mode": "auto",
}

state = {"cfg": dict(DEFAULTS), "log": []}
lock = threading.Lock()


def chunks(text, n=20):
    size = max(1, -(-len(text) // n))
    return [text[i:i + size] for i in range(0, len(text), size)]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path.endswith("/models"):
            return self._json(200, {"object": "list", "data": [{"id": "mock-model"}]})
        if self.path == "/_log":
            with lock:
                return self._json(200, state["log"])
        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/_config":
            with lock:
                state["cfg"].update(self._body())
                return self._json(200, state["cfg"])
        if self.path == "/_reset":
            with lock:
                state["cfg"] = dict(DEFAULTS)
                state["log"] = []
            return self._json(200, {"ok": True})
        if not self.path.endswith("/chat/completions"):
            return self._json(404, {"error": "not found"})

        req = self._body()
        with lock:
            cfg = dict(state["cfg"])
            entry = {"request": req, "disconnected": False, "time": time.time()}
            state["log"].append(entry)

        try:
            # Wait in small steps so a client disconnect is noticed quickly.
            end = time.time() + cfg["delay"]
            while time.time() < end:
                r, _, _ = select.select([self.connection], [], [], 0.05)
                if r and self.connection.recv(1, socket.MSG_PEEK) == b"":
                    raise ConnectionResetError("client went away")

            if cfg["status"] != 200:
                return self._json(cfg["status"], {"error": {"message": "mock failure"}})

            if req.get("stream") and cfg["stream_mode"] != "never":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(b": keep-alive comment\n\n")
                for piece in chunks(cfg["reply"]):
                    data = {"choices": [{"index": 0, "delta": {"content": piece}}]}
                    self.wfile.write(("data: " + json.dumps(data) + "\n\n").encode())
                    self.wfile.flush()
                    time.sleep(cfg["chunk_delay"])
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self.close_connection = True
            else:
                self._json(200, {"choices": [{"index": 0, "message": {"role": "assistant", "content": cfg["reply"]},
                                              "finish_reason": "stop"}]})
        except (BrokenPipeError, ConnectionResetError):
            with lock:
                entry["disconnected"] = True


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    print("mock llm on", port, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
