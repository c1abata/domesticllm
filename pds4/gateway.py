from __future__ import annotations

import argparse
import hmac
import http.client
import http.server
import json
import os
import pathlib
import threading
import urllib.parse
from typing import Any

from .common import PDS4Error, read_json
from .manifest import validate_manifest


WEB_ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
              "/app.css": ("app.css", "text/css; charset=utf-8"),
              "/app.js": ("app.js", "text/javascript; charset=utf-8")}
WEB_CSP = ("default-src 'self'; base-uri 'none'; connect-src 'self'; font-src 'self'; "
           "form-action 'none'; frame-ancestors 'none'; img-src 'self' data:; object-src 'none'; "
           "script-src 'self'; style-src 'self'")
ALLOWED_PATHS = {"/v1/chat/completions", "/v1/responses", "/v1/messages"}
HOP_HEADERS = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade"}


def load_catalog(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    catalog = {}
    for path in sorted(root.glob("*.json")):
        manifest = validate_manifest(read_json(path))
        catalog[manifest["id"]] = manifest
    if not catalog:
        raise PDS4Error("model catalog is empty")
    return catalog


def load_key(path: pathlib.Path) -> str:
    info = os.lstat(path)
    if path.is_symlink() or info.st_mode & 0o037:
        raise PDS4Error("gateway key must be a regular file with mode 0640 or stricter")
    key = path.read_text(encoding="utf-8").splitlines()[0]
    if len(key) < 32 or any(char in key for char in "\r\n"):
        raise PDS4Error("invalid gateway key")
    return key


def route_request(routes: dict[str, Any], catalog: dict[str, dict[str, Any]], model: str) -> tuple[int, str]:
    manifest = catalog.get(model)
    if not manifest:
        raise PDS4Error("model_not_loaded")
    lane = manifest["lane"]
    state = routes.get(lane, {})
    if state.get("status") == "warming" and state.get("model") == model:
        raise PDS4Error("warming")
    if state.get("status") != "ready" or state.get("model") != model:
        raise PDS4Error("model_not_loaded")
    return (8082 if lane == "flash" else 8085), lane


def anthropic_to_openai(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("stream") or any(name in payload for name in ("tools", "tool_choice")):
        raise PDS4Error("unsupported_feature")
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise PDS4Error("invalid_request")
    converted = []
    system = payload.get("system")
    if isinstance(system, str):
        converted.append({"role": "system", "content": system})
    for item in messages:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise PDS4Error("unsupported_feature")
        content = item.get("content")
        if not isinstance(content, str):
            raise PDS4Error("unsupported_feature")
        converted.append({"role": item["role"], "content": content})
    return {"model": payload.get("model"), "messages": converted,
            "max_tokens": payload.get("max_tokens", 1024),
            "temperature": payload.get("temperature", 1.0), "stream": False}


def openai_to_anthropic(payload: dict[str, Any], model: str) -> dict[str, Any]:
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise PDS4Error("invalid_backend_response")
    message = choices[0].get("message", {})
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise PDS4Error("invalid_backend_response")
    usage = payload.get("usage", {})
    return {"id": payload.get("id", "msg_local"), "type": "message", "role": "assistant",
            "model": model, "content": [{"type": "text", "text": content}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": usage.get("prompt_tokens", 0),
                      "output_tokens": usage.get("completion_tokens", 0)}}


class Gateway(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PDS4Gateway/1"

    def _error(self, status: int, code: str, **details: Any) -> None:
        error = {"code": code, **details}
        body = (json.dumps({"error": error}, separators=(",", ":")) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _authorized(self) -> bool:
        return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + self.server.api_key)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if not parsed.query and parsed.path in WEB_ASSETS:
            self._web(parsed.path)
            return
        if not self._authorized():
            self._error(401, "authentication_required")
            return
        if parsed.path == "/health" and not parsed.query:
            self._json(200, {"status": "ok", "routes": self._routes()})
        elif parsed.path == "/v1/models" and not parsed.query:
            self._models()
        else:
            self._error(404, "route_not_available")

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        if not self._authorized():
            self._error(401, "authentication_required")
            return
        if parsed.query or parsed.path not in ALLOWED_PATHS:
            self._error(404, "route_not_available")
            return
        if self.headers.get("Transfer-Encoding"):
            self._error(400, "unsupported_request_framing")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._error(400, "invalid_content_length")
            return
        if length < 2 or length > self.server.max_body:
            self._error(413, "request_too_large")
            return
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise PDS4Error("invalid_request")
            model = payload.get("model")
            if not isinstance(model, str):
                raise PDS4Error("invalid_request")
            routes = self._routes()
            port, lane = route_request(routes, self.server.catalog, model)
            backend_path = parsed.path
            translated = parsed.path == "/v1/messages" and lane == "fast"
            if translated:
                payload = anthropic_to_openai(payload)
                backend_path = "/v1/chat/completions"
            self._proxy(port, backend_path, payload, model, translated)
        except json.JSONDecodeError:
            self._error(400, "invalid_json")
        except PDS4Error as exc:
            code = str(exc)
            if code == "warming":
                self._error(503, code, requested=model)
            elif code == "model_not_loaded":
                fast = self._routes().get("fast", {})
                self._error(409, code, requested=model, active_fast_model=fast.get("model"))
            else:
                self._error(400, code)

    def _routes(self) -> dict[str, Any]:
        try:
            value = read_json(self.server.routes_file)
            return value if isinstance(value, dict) else {}
        except PDS4Error:
            return {}

    def _models(self) -> None:
        routes = self._routes()
        data = []
        for lane in ("flash", "fast"):
            state = routes.get(lane, {})
            model = state.get("model")
            if state.get("status") == "ready" and model in self.server.catalog:
                data.append({"id": model, "object": "model", "owned_by": "pds4", "pds4_lane": lane})
        self._json(200, {"object": "list", "data": data, "pds4": {"lanes": routes}})

    def _proxy(self, port: int, path: str, payload: dict[str, Any], model: str, translated: bool) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        connection = self.server.backend_connection("127.0.0.1", port, self.server.timeout)
        headers = {"Content-Type": "application/json", "Accept": self.headers.get("Accept", "application/json")}
        if port == 8085:
            headers["Authorization"] = "Bearer " + self.server.api_key
        try:
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            if translated:
                backend_body = response.read(self.server.max_body)
                if not 200 <= response.status < 300:
                    self._error(response.status, "backend_error")
                    return
                self._json(200, openai_to_anthropic(json.loads(backend_body), model))
                return
            self.send_response(response.status)
            content_type = response.getheader("Content-Type", "application/json")
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            while chunk := response.read(65536):
                self.wfile.write(chunk)
                if "text/event-stream" in content_type:
                    self.wfile.flush()
            self.close_connection = True
        except (OSError, http.client.HTTPException, json.JSONDecodeError):
            self._error(502, "backend_unavailable")
        finally:
            connection.close()

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _web(self, path: str) -> None:
        filename, content_type = WEB_ASSETS[path]
        target = self.server.web_root / filename
        if target.is_symlink() or not target.is_file():
            self._error(404, "web_not_installed")
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Security-Policy", WEB_CSP)
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), geolocation=(), microphone=()")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pds4-gateway")
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--routes", default="/run/pds4/routes.json")
    parser.add_argument("--catalog", default="/etc/pds4/models.d")
    parser.add_argument("--web-root", default="/usr/share/pds4/web")
    parser.add_argument("--api-key-file", default="/etc/pds4/gateway.key")
    parser.add_argument("--max-body", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)
    server = Server((args.listen, args.port), Gateway)
    server.api_key = load_key(pathlib.Path(args.api_key_file))
    server.routes_file = pathlib.Path(args.routes)
    server.catalog = load_catalog(pathlib.Path(args.catalog))
    server.web_root = pathlib.Path(args.web_root)
    server.max_body = args.max_body
    server.timeout = args.timeout
    server.backend_connection = lambda host, port, timeout: http.client.HTTPConnection(host, port, timeout=timeout)
    server.serve_forever(0.25)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
