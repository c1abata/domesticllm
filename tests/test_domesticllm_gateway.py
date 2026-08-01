import http.client
import http.server
import importlib.util
import os
import pathlib
import tempfile
import threading
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "domesticllm-gateway.py"
SPEC = importlib.util.spec_from_file_location("domesticllm_gateway", SCRIPT)
GATEWAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATEWAY)


class Backend(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        body = b'{"status":"ok"}\n'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.backend = http.server.HTTPServer(("127.0.0.1", 0), Backend)
        self.backend_thread = threading.Thread(target=self.backend.serve_forever, daemon=True)
        self.backend_thread.start()
        self.gateway = GATEWAY.Server(("127.0.0.1", 0), GATEWAY.Gateway)
        self.gateway.api_key = "x" * 48
        self.gateway.backend_host = "127.0.0.1"
        self.gateway.backend_port = self.backend.server_port
        self.gateway.max_body = 1024
        self.gateway.timeout = 5
        self.gateway.slots = threading.BoundedSemaphore(1)
        self.gateway_thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.gateway_thread.start()

    def tearDown(self):
        self.gateway.shutdown()
        self.backend.shutdown()
        self.gateway.server_close()
        self.backend.server_close()

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


if __name__ == "__main__":
    unittest.main()
