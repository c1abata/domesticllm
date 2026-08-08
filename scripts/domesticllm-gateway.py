#!/usr/bin/env python3
"""Small authenticated reverse proxy for the controlled local OpenAI API."""

from __future__ import annotations

import argparse
import hmac
import http.client
import http.server
import json
import os
import pathlib
import socket
import threading
import urllib.parse

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade"}
WEB_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
WEB_CSP = ("default-src 'self'; base-uri 'none'; connect-src 'self'; "
           "font-src 'self'; form-action 'none'; frame-ancestors 'none'; "
           "img-src 'self' data:; object-src 'none'; script-src 'self'; style-src 'self'")
# DS4 exposes a compatibility alias for the same Flash GGUF. Keep the public
# catalog canonical so the Web UI does not present a duplicate model.
HIDDEN_MODEL_ALIASES = {"deepseek-v4-pro"}


def read_chunked(stream, max_body: int) -> bytes:
    body = bytearray()
    while True:
        line = stream.readline(129)
        if not line or len(line) > 128 or not line.endswith(b"\r\n"):
            raise ValueError("invalid chunk framing")
        try:
            size = int(line[:-2].split(b";", 1)[0], 16)
        except ValueError as exc:
            raise ValueError("invalid chunk size") from exc
        if size < 0 or len(body) + size > max_body:
            raise OverflowError("request too large")
        if size == 0:
            while True:
                trailer = stream.readline(8193)
                if not trailer or len(trailer) > 8192:
                    raise ValueError("invalid chunk trailer")
                if trailer == b"\r\n":
                    return bytes(body)
        chunk = stream.read(size)
        if len(chunk) != size or stream.read(2) != b"\r\n":
            raise ValueError("incomplete chunk")
        body.extend(chunk)


def backend_port_for_request(default_port: int, fast_port: int | None,
                             fast_models: set[str], body: bytes | None) -> int:
    if not body or not fast_port:
        return default_port
    try:
        model = json.loads(body).get("model")
    except (AttributeError, json.JSONDecodeError, UnicodeDecodeError):
        return default_port
    return fast_port if model in fast_models else default_port


def fetch_models(host: str, port: int, timeout: int, key: str | None = None) -> list[dict]:
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    headers = {"Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        connection.request("GET", "/v1/models", headers=headers)
        response = connection.getresponse()
        body = response.read(1024 * 1024)
        if not 200 <= response.status < 300:
            raise OSError(f"model catalog returned HTTP {response.status}")
        payload = json.loads(body)
        models = payload.get("data")
        if not isinstance(models, list):
            raise ValueError("model catalog has no data array")
        return [item for item in models if isinstance(item, dict) and isinstance(item.get("id"), str)]
    finally:
        connection.close()


class Gateway(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DomesticLLMGateway/1"

    def log_message(self, fmt: str, *args) -> None:
        # Never log Authorization or request bodies.
        super().log_message(fmt, *args)

    def _json_error(self, status: int, message: str) -> None:
        body = ('{"error":{"message":"' + message + '"}}\n').encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.api_key
        return hmac.compare_digest(supplied, expected)

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def _proxy(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if self.command == "GET" and not parsed.query and not parsed.fragment and parsed.path in WEB_ASSETS:
            self._serve_web(parsed.path)
            return
        if not self._authorized():
            self._json_error(401, "authentication required")
            return
        if parsed.query or parsed.fragment or not (parsed.path == "/health" or parsed.path.startswith("/v1/")):
            self._json_error(404, "route not available")
            return
        if self.command == "GET" and parsed.path == "/v1/models" and self.server.fast_backend_port:
            self._serve_models()
            return
        transfer_encoding = self.headers.get("Transfer-Encoding", "").casefold()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json_error(400, "invalid content length")
            return
        if length < 0 or length > self.server.max_body:
            self._json_error(413, "request too large")
            return
        backend = None
        acquired = False
        try:
            if transfer_encoding:
                if transfer_encoding != "chunked" or self.headers.get("Content-Length"):
                    raise ValueError("unsupported request framing")
                body = read_chunked(self.rfile, self.server.max_body)
            else:
                body = self.rfile.read(length) if length else None
            slot = self.server.slots[backend_port_for_request(
                self.server.backend_port, self.server.fast_backend_port,
                self.server.fast_models, body)]
            acquired = slot.acquire(timeout=self.server.timeout)
            if not acquired:
                self._json_error(429, "model is busy")
                return
            backend_port = backend_port_for_request(
                self.server.backend_port, self.server.fast_backend_port,
                self.server.fast_models, body)
            backend = http.client.HTTPConnection(self.server.backend_host, backend_port,
                                                 timeout=self.server.timeout)
            headers = {name: value for name, value in self.headers.items()
                       if name.lower() not in HOP_HEADERS | {"authorization", "host", "content-length"}}
            if backend_port == self.server.fast_backend_port:
                headers["Authorization"] = "Bearer " + self.server.api_key
            if body is not None:
                headers["Content-Length"] = str(len(body))
            backend.request(self.command, parsed.path, body=body, headers=headers)
            response = backend.getresponse()
            self.send_response(response.status)
            content_type = response.getheader("Content-Type", "")
            for name, value in response.getheaders():
                if name.lower() not in HOP_HEADERS | {"content-length"}:
                    self.send_header(name, value)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if "text/event-stream" in content_type:
                while True:
                    line = response.readline()
                    if not line:
                        break
                    self.wfile.write(line)
                    self.wfile.flush()
            else:
                while True:
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
            self.close_connection = True
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (ValueError, OverflowError, OSError, http.client.HTTPException) as exc:
            if not self.wfile.closed:
                try:
                    self._json_error(502, "backend unavailable")
                except OSError:
                    pass
            self.log_error("backend failure: %s", type(exc).__name__)
        finally:
            if backend:
                backend.close()
            if acquired:
                slot.release()

    def _serve_web(self, path: str) -> None:
        if not self.server.web_root:
            self._json_error(404, "web interface not installed")
            return
        filename, content_type = WEB_ASSETS[path]
        target = self.server.web_root / filename
        try:
            body = target.read_bytes()
        except OSError:
            self._json_error(404, "web interface not installed")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", WEB_CSP)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def _serve_models(self) -> None:
        data: list[dict] = []
        status = {}
        lanes = (
            ("capacity", self.server.backend_port, None),
            ("fast", self.server.fast_backend_port, self.server.api_key),
        )
        seen = set()
        for lane, port, key in lanes:
            try:
                models = fetch_models(self.server.backend_host, port, min(self.server.timeout, 10), key)
                status[lane] = "online"
            except (OSError, http.client.HTTPException, json.JSONDecodeError, ValueError):
                status[lane] = "offline"
                continue
            for item in models:
                model_id = item["id"]
                if model_id in HIDDEN_MODEL_ALIASES:
                    continue
                if model_id in seen:
                    continue
                seen.add(model_id)
                model = dict(item)
                model["domesticllm_lane"] = lane
                data.append(model)
        if not data and all(value == "offline" for value in status.values()):
            self._json_error(502, "model backends unavailable")
            return
        body = json.dumps({"object": "list", "data": data,
                           "domesticllm": {"backends": status}}, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def load_key(path: str) -> str:
    info = os.lstat(path)
    if os.path.islink(path) or info.st_mode & 0o037:
        raise ValueError("API key file must not be a symlink and must be mode 0640 or stricter")
    with open(path, encoding="utf-8") as source:
        key = source.readline().rstrip("\r\n")
    if len(key) < 32 or any(char in key for char in "\r\n"):
        raise ValueError("invalid API key")
    return key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8083)
    parser.add_argument("--fast-backend-port", type=int)
    parser.add_argument("--fast-models", default="dolphin,qwen,cyber-uncensored")
    parser.add_argument("--web-root")
    parser.add_argument("--default-concurrency", type=int, default=1)
    parser.add_argument("--fast-concurrency", type=int, default=1)
    parser.add_argument("--api-key-file", required=True)
    parser.add_argument("--max-body", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.backend_host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("backend must be loopback")
    if args.default_concurrency < 1 or args.fast_concurrency < 1:
        parser.error("concurrency must be at least one")
    key = load_key(args.api_key_file)
    server = Server((args.listen, args.port), Gateway)
    server.api_key = key
    server.backend_host = args.backend_host
    server.backend_port = args.backend_port
    server.fast_backend_port = args.fast_backend_port
    server.fast_models = {model.strip() for model in args.fast_models.split(",") if model.strip()}
    server.max_body = args.max_body
    server.timeout = args.timeout
    server.web_root = pathlib.Path(args.web_root).resolve() if args.web_root else None
    server.slots = {args.backend_port: threading.BoundedSemaphore(args.default_concurrency)}
    if args.fast_backend_port:
        server.slots[args.fast_backend_port] = threading.BoundedSemaphore(args.fast_concurrency)
    server.serve_forever(poll_interval=0.25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
