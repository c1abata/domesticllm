#!/usr/bin/env python3
"""Small authenticated reverse proxy for a loopback-only OpenAI API."""

from __future__ import annotations

import argparse
import hmac
import http.client
import http.server
import json
import os
import socket
import threading
import urllib.parse

HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade"}


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
        if not self._authorized():
            self._json_error(401, "authentication required")
            return
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.query or parsed.fragment or not (parsed.path == "/health" or parsed.path.startswith("/v1/")):
            self._json_error(404, "route not available")
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
            acquired = self.server.slots.acquire(timeout=self.server.timeout)
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
                self.server.slots.release()


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
    parser.add_argument("--fast-models", default="mistral-small,dolphin,qwen3-coder,cyber-uncensored")
    parser.add_argument("--api-key-file", required=True)
    parser.add_argument("--max-body", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if args.backend_host not in {"127.0.0.1", "::1", "localhost"}:
        parser.error("backend must be loopback")
    key = load_key(args.api_key_file)
    server = Server((args.listen, args.port), Gateway)
    server.api_key = key
    server.backend_host = args.backend_host
    server.backend_port = args.backend_port
    server.fast_backend_port = args.fast_backend_port
    server.fast_models = {model.strip() for model in args.fast_models.split(",") if model.strip()}
    server.max_body = args.max_body
    server.timeout = args.timeout
    server.slots = threading.BoundedSemaphore(1)
    server.serve_forever(poll_interval=0.25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
