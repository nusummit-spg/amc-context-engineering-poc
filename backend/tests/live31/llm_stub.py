"""A local stand-in for the Groq chat-completions API, used ONLY by the live HTTP suite.

The LLM provider is not one of the systems this suite certifies (and no provider key exists
offline). The app talks to this server through the real Groq SDK by setting GROQ_BASE_URL.

To keep the end-to-end check meaningful the stub is GROUNDED: its answer is built from the
retrieval context the app puts in the prompt, so an answer that contains the right tenant's fact
proves the right chunk travelled from the verified index through the orchestrator to the model
input. Structured (JSON-schema) requests get a minimal valid instance of the requested schema.
"""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARKER = "[SYNTHETIC-FIXTURE]"


def _instance(schema, defs=None):
    """Smallest valid JSON instance of a JSON schema."""
    defs = defs or schema.get("$defs", {}) if isinstance(schema, dict) else {}
    if not isinstance(schema, dict):
        return None
    if "$ref" in schema:
        return _instance(defs.get(schema["$ref"].split("/")[-1], {}), defs)
    if "enum" in schema:
        return schema["enum"][0]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [o for o in schema[key] if o.get("type") != "null"] or schema[key]
            return _instance(options[0], defs)
    t = schema.get("type")
    if t == "object":
        props = schema.get("properties", {})
        return {k: _instance(v, defs) for k, v in props.items() if k in schema.get("required", props.keys())}
    if t == "array":
        return []
    if t == "string":
        return "synthetic"
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return False
    return None


def _grounded_answer(prompt: str) -> str:
    facts = []
    for line in prompt.splitlines():
        if MARKER in line:
            facts.append(line.split(MARKER, 1)[1].strip(" -*:\t"))
    if not facts:
        return "The provided sources do not contain enough information to answer."
    # Prefer a line the question shares words with; otherwise the first retrieved fact.
    return f"{facts[0]} [1]"


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):          # keep test output quiet
        pass

    def _send(self, status, body: bytes, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(200, json.dumps({"object": "list", "data": [{"id": "stub-model"}]}).encode())

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length) or b"{}")
        self.server.calls.append(req)
        if self.server.fail_next:
            self.server.fail_next -= 1
            return self._send(500, json.dumps({"error": {"message": "stub provider outage"}}).encode())
        messages = req.get("messages", [])
        prompt = "\n".join(str(m.get("content", "")) for m in messages)
        rf = req.get("response_format") or {}
        if rf.get("type") == "json_schema":
            content = json.dumps(_instance(rf["json_schema"].get("schema", {})))
        elif rf.get("type") == "json_object":
            content = "{}"
        else:
            content = _grounded_answer(prompt)
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            words = content.split(" ")
            for i, w in enumerate(words):
                chunk = {"id": "c1", "object": "chat.completion.chunk", "model": "stub-model",
                         "choices": [{"index": 0, "delta": {"content": w + (" " if i < len(words) - 1 else "")},
                                      "finish_reason": None}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
                self.wfile.flush()
                if self.server.stream_delay:
                    time.sleep(self.server.stream_delay)
            done = {"id": "c1", "object": "chat.completion.chunk", "model": "stub-model",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            self.wfile.write(f"data: {json.dumps(done)}\n\ndata: [DONE]\n\n".encode())
            return
        body = {"id": "c1", "object": "chat.completion", "created": int(time.time()), "model": "stub-model",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        self._send(200, json.dumps(body).encode())


class LlmStub:
    def __init__(self, port: int = 0):
        self.server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
        self.server.calls = []
        self.server.fail_next = 0
        self.server.stream_delay = 0.0
        self.port = self.server.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    @property
    def calls(self):
        return self.server.calls

    def prompts(self) -> str:
        return "\n".join(str(m.get("content", "")) for c in self.calls for m in c.get("messages", []))
