import http.client
import http.server
import io
import importlib.util
import os
import pathlib
import tempfile
import threading
import unittest
import json


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "domesticllm-gateway.py"
SPEC = importlib.util.spec_from_file_location("domesticllm_gateway", SCRIPT)
GATEWAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATEWAY)


class Backend(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            body = json.dumps({"object": "list", "data": [{
                "id": self.server.model_id, "object": "model", "owned_by": "local"
            }]}).encode()
        else:
            body = b'{"status":"ok"}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.backend = http.server.HTTPServer(("127.0.0.1", 0), Backend)
        self.backend.model_id = "deepseek-v4-flash"
        self.backend_thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.backend_thread.start()
        self.fast_backend = http.server.HTTPServer(("127.0.0.1", 0), Backend)
        self.fast_backend.model_id = "qwen"
        self.fast_backend_thread = threading.Thread(target=self.fast_backend.serve_forever, daemon=True)
        self.fast_backend_thread.start()
        self.gateway = GATEWAY.Server(("127.0.0.1", 0), GATEWAY.Gateway)
        self.gateway.api_key = "x" * 48
        self.gateway.backend_host = "127.0.0.1"
        self.gateway.backend_port = self.backend.server_port
        self.gateway.fast_backend_port = self.fast_backend.server_port
        self.gateway.fast_models = {"dolphin", "qwen", "cyber-uncensored"}
        self.gateway.max_body = 1024
        self.gateway.timeout = 5
        self.gateway.web_root = SCRIPT.parents[1] / "web"
        self.gateway.slots = {
            self.backend.server_port: threading.BoundedSemaphore(1),
            self.fast_backend.server_port: threading.BoundedSemaphore(1),
        }
        self.gateway_thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.gateway_thread.start()

    def tearDown(self):
        self.gateway.shutdown()
        self.backend.shutdown()
        self.fast_backend.shutdown()
        self.gateway.server_close()
        self.backend.server_close()
        self.fast_backend.server_close()

    def request(self, path="/health", key=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=5)
        headers = {"Authorization": "Bearer " + key} if key else {}
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def test_anonymous_request_is_rejected(self):
        status, _ = self.request()
        self.assertEqual(status, 401)

    def test_authenticated_health_is_proxied(self):
        status, body = self.request(key="x" * 48)
        self.assertEqual(status, 200)
        self.assertIn(b'"ok"', body)

    def test_web_interface_is_public_but_contains_no_secret(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.gateway.server_port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        body = response.read()
        self.assertEqual(response.status, 200)
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
        self.assertEqual(response.getheader("Cross-Origin-Resource-Policy"), "same-origin")
        self.assertIn(b"DomesticLLM", body)
        self.assertNotIn(("x" * 48).encode(), body)
        connection.close()

    def test_model_catalog_aggregates_live_lanes(self):
        status, body = self.request(path="/v1/models", key="x" * 48)
        self.assertEqual(status, 200)
        payload = json.loads(body)
        models = {item["id"]: item["domesticllm_lane"] for item in payload["data"]}
        self.assertEqual(models, {"deepseek-v4-flash": "capacity", "qwen": "fast"})

    def test_routes_are_allowlisted(self):
        status, _ = self.request(path="/admin", key="x" * 48)
        self.assertEqual(status, 404)

    def test_key_file_permissions_are_checked(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as target:
            target.write("x" * 48 + "\n")
            path = target.name
        try:
            os.chmod(path, 0o600)
            self.assertEqual(GATEWAY.load_key(path), "x" * 48)
            os.chmod(path, 0o644)
            with self.assertRaises(ValueError):
                GATEWAY.load_key(path)
        finally:
            os.unlink(path)

    def test_explicit_fast_model_is_routed(self):
        body = b'{"model":"dolphin","messages":[]}'
        selected = GATEWAY.backend_port_for_request(8083, 8085, {"dolphin", "qwen", "cyber-uncensored"}, body)
        self.assertEqual(selected, 8085)

    def test_qwen_coder_is_routed_to_fast_lane(self):
        body = b'{"model":"qwen","messages":[]}'
        selected = GATEWAY.backend_port_for_request(8083, 8085, {"qwen"}, body)
        self.assertEqual(selected, 8085)

    def test_cyber_uncensored_is_routed_to_fast_lane(self):
        body = b'{"model":"cyber-uncensored","messages":[]}'
        selected = GATEWAY.backend_port_for_request(8083, 8085, {"cyber-uncensored"}, body)
        self.assertEqual(selected, 8085)

    def test_chunked_request_body_is_decoded_and_bounded(self):
        wire = io.BytesIO(b"4\r\nWiki\r\n5\r\npedia\r\n0\r\n\r\n")
        self.assertEqual(GATEWAY.read_chunked(wire, 9), b"Wikipedia")
        with self.assertRaises(OverflowError):
            GATEWAY.read_chunked(io.BytesIO(b"a\r\n0123456789\r\n0\r\n\r\n"), 9)

    def test_unknown_or_malformed_model_stays_on_default(self):
        for body in (b'{"model":"deepseek-v4-flash"}', b'not-json'):
            with self.subTest(body=body):
                self.assertEqual(
                    GATEWAY.backend_port_for_request(8083, 8085, {"dolphin"}, body), 8083)


if __name__ == "__main__":
    unittest.main()
