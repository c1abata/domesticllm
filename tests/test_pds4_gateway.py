import http.client
import http.server
import json
import tempfile
import threading
import unittest
from pathlib import Path

from pds4 import gateway
from pds4.common import atomic_write, canonical_json


KEY = "k" * 48


class Backend(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        content = "OK " + request["model"]
        payload = json.dumps({"id": "local", "choices": [{"message": {"role": "assistant", "content": content}}],
                              "usage": {"prompt_tokens": 2, "completion_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.routes = root / "routes.json"
        self.web = root / "web"
        self.web.mkdir()
        for name in ("index.html", "app.css", "app.js"):
            (self.web / name).write_text(name, encoding="utf-8")
        self.backend = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        self.backend_thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.backend_thread.start()
        self.server = gateway.Server(("127.0.0.1", 0), gateway.Gateway)
        self.server.api_key = KEY
        self.server.routes_file = self.routes
        self.server.catalog = {
            "flash-q2": {"id": "flash-q2", "lane": "flash"},
            "qwen3-coder-q4": {"id": "qwen3-coder-q4", "lane": "fast"},
            "mistral-small-q4": {"id": "mistral-small-q4", "lane": "fast"},
        }
        self.server.web_root = self.web
        self.server.max_body = 1024 * 1024
        self.server.timeout = 5
        self.server.backend_connection = lambda host, port, timeout: http.client.HTTPConnection(
            host, self.backend.server_port, timeout=timeout)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.backend.shutdown()
        self.backend.server_close()
        self.temporary.cleanup()

    def request(self, method, path, body=None, authorized=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if authorized:
            headers["Authorization"] = "Bearer " + KEY
        connection.request(method, path, body=json.dumps(body).encode() if body else None, headers=headers)
        response = connection.getresponse()
        payload = response.read()
        connection.close()
        return response.status, json.loads(payload) if payload.startswith(b"{") else payload, response.headers

    def set_routes(self, fast_status="ready", fast_model="qwen3-coder-q4"):
        value = {"schema": 1, "flash": {"status": "ready", "model": "flash-q2"},
                 "fast": {"status": fast_status, "model": fast_model}}
        atomic_write(self.routes, canonical_json(value))

    def test_catalog_contains_only_ready_models(self):
        self.set_routes("warming")
        status, payload, _ = self.request("GET", "/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in payload["data"]], ["flash-q2"])

    def test_non_active_fast_model_is_not_loaded(self):
        self.set_routes()
        status, payload, _ = self.request("POST", "/v1/chat/completions",
                                          {"model": "mistral-small-q4", "messages": []})
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "model_not_loaded")

    def test_warming_is_explicit(self):
        self.set_routes("warming")
        status, payload, _ = self.request("POST", "/v1/chat/completions",
                                          {"model": "qwen3-coder-q4", "messages": []})
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"]["code"], "warming")

    def test_ready_fast_model_is_proxied(self):
        self.set_routes()
        status, payload, _ = self.request("POST", "/v1/chat/completions",
                                          {"model": "qwen3-coder-q4", "messages": []})
        self.assertEqual(status, 200)
        self.assertIn("OK", payload["choices"][0]["message"]["content"])

    def test_streaming_anthropic_fast_request_is_explicitly_unsupported(self):
        self.set_routes()
        status, payload, _ = self.request("POST", "/v1/messages",
                                          {"model": "qwen3-coder-q4", "messages": [], "stream": True})
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "unsupported_feature")

    def test_authentication_and_csp(self):
        status, _, _ = self.request("GET", "/health", authorized=False)
        self.assertEqual(status, 401)
        status, _, headers = self.request("GET", "/", authorized=False)
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])

    def test_anthropic_translation_shape(self):
        self.set_routes()
        status, payload, _ = self.request("POST", "/v1/messages",
                                          {"model": "qwen3-coder-q4", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8})
        self.assertEqual(status, 200)
        self.assertEqual(payload["type"], "message")


if __name__ == "__main__":
    unittest.main()
