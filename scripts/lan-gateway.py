#!/usr/bin/env python3
"""One LAN gateway, one active local inference backend, no external calls."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import secrets
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

UI = Path(__file__).parents[1] / "web-lan" / "index.html"

class Gateway:
    def __init__(self, config_path: Path, state_path: Path):
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        if self.config.get("version") != 1 or len(self.config.get("models", {})) > 3:
            raise ValueError("invalid model catalog")
        self.models: dict[str, dict[str, Any]] = self.config["models"]
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path = state_path.parent / "api.token"
        if not self.token_path.exists():
            self.token_path.write_text(secrets.token_urlsafe(32) + "\n", encoding="utf-8")
        self.token_path.chmod(0o600)
        self.api_token = self.token_path.read_text(encoding="utf-8").strip()
        self.lock = threading.RLock()
        self.process: subprocess.Popen[bytes] | None = None
        self.active: str | None = None
        self.active_runtime: dict[str, Any] = {}
        self.session_started_at: float | None = None
        self.session_requests = 0
        self.last_generation: dict[str, Any] | None = None

    def save_state(self, status: str, message: str = "") -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.status(status, message)), encoding="utf-8")
        os.replace(temporary, self.state_path)

    def status(self, status: str = "ready", message: str = "") -> dict[str, Any]:
        now = time.time()
        return {"active_model": self.active, "status": status, "message": message,
                "updated_at": now, "session": {"started_at": self.session_started_at,
                "elapsed_seconds": round(now - self.session_started_at, 3) if self.session_started_at else 0,
                "requests": self.session_requests, "runtime": self.active_runtime,
                "last_generation": self.last_generation}}

    @staticmethod
    def _replace_option(args: list[str], option: str, value: str) -> None:
        args[args.index(option) + 1] = value

    def command(self, name: str, runtime: dict[str, Any] | None = None) -> list[str]:
        profile = self.models[name]
        args = list(profile["args"])
        runtime = runtime or {}
        unknown = set(runtime) - {"context", "parallel", "flash_attention", "kv_cache"}
        if unknown: raise ValueError("unsupported runtime settings: " + ", ".join(sorted(unknown)))
        if profile["engine"] == "llama":
            if "context" in runtime:
                context = int(runtime["context"])
                if context not in {2048, 4096, 8192, 16384}: raise ValueError("unsupported context size")
                self._replace_option(args, "--ctx-size", str(context))
            if "parallel" in runtime:
                parallel = int(runtime["parallel"])
                if parallel not in {1, 2, 3, 4}: raise ValueError("unsupported parallel slot count")
                self._replace_option(args, "--parallel", str(parallel))
            if "flash_attention" in runtime:
                value = str(runtime["flash_attention"])
                if value not in {"auto", "on", "off"}: raise ValueError("invalid flash attention mode")
                self._replace_option(args, "--flash-attn", value)
            if "kv_cache" in runtime:
                value = str(runtime["kv_cache"])
                if value not in {"q4_0", "q8_0", "f16"}: raise ValueError("invalid KV cache type")
                self._replace_option(args, "--cache-type-k", value); self._replace_option(args, "--cache-type-v", value)
        if profile["engine"] == "llama":
            binary = os.environ.get("LLAMA_SERVER_BIN", "/srv/local-ai/build/llama.cpp-876a4321163249c43ca4e986818fab5ab081f282/build-cuda/bin/llama-server")
            return [binary, "--model", profile["model"], "--host", "127.0.0.1", "--port", str(profile["port"]), *args]
        binary = os.environ.get("DS4_SERVER_BIN", "/home/ale/pds4-deploy/build/offline-ds4-source/ds4-server")
        return [binary, "--model", profile["model"], "--host", "127.0.0.1", "--port", str(profile["port"]), *args]

    @staticmethod
    def verify_model(profile: dict[str, Any]) -> None:
        artifacts = [(profile.get("model"), profile.get("sha256"), "model")]
        if profile.get("projector"):
            artifacts.append((profile.get("projector"), profile.get("projector_sha256"), "projector"))
        for raw_path, expected, label in artifacts:
            path = Path(str(raw_path))
            if not path.is_file() or not isinstance(expected, str) or len(expected) != 64:
                raise RuntimeError(f"{label} file or pinned SHA-256 is missing")
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != expected:
                raise RuntimeError(f"{label} SHA-256 does not match the catalog")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try: self.process.wait(timeout=300)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=30)
        self.process, self.active, self.active_runtime = None, None, {}
        self.session_started_at, self.session_requests, self.last_generation = None, 0, None

    def ready(self, port: int) -> bool:
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            connection.request("GET", "/v1/models")
            response = connection.getresponse(); response.read(); connection.close()
            return 200 <= response.status < 300
        except OSError: return False

    def activate(self, name: str, runtime: dict[str, Any] | None = None) -> dict[str, Any]:
        if name not in self.models: raise ValueError("model is not in the catalog")
        profile = self.models[name]
        if not profile.get("admitted", False): raise PermissionError(profile.get("reason", "model is not admitted"))
        with self.lock:
            normalized_runtime = runtime or {}
            if self.active == name and self.process and self.process.poll() is None and getattr(self, "active_runtime", {}) == normalized_runtime: return profile
            self.verify_model(profile)
            self.stop(); self.save_state("loading", name)
            log = self.state_path.parent / f"{name}.log"
            with log.open("ab") as output:
                self.process = subprocess.Popen(self.command(name, normalized_runtime), stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            self.active, self.active_runtime = name, normalized_runtime
            self.session_started_at, self.session_requests, self.last_generation = time.time(), 0, None
            deadline = time.monotonic() + 15 * 60
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    self.save_state("failed", f"backend exited; inspect {log}")
                    self.active = None
                    raise RuntimeError("backend failed during startup")
                if self.ready(int(profile["port"])):
                    self.save_state("ready")
                    return profile
                time.sleep(1)
            self.stop(); self.save_state("failed", "backend readiness timeout")
            raise RuntimeError("backend readiness timeout")

    def record_generation(self, response: dict[str, Any]) -> None:
        timings, usage = response.get("timings", {}), response.get("usage", {})
        if not isinstance(timings, dict) or not isinstance(usage, dict): return
        self.session_requests += 1
        self.last_generation = {"finished_at": time.time(),
            "prompt_tokens": usage.get("prompt_tokens", timings.get("prompt_n")),
            "generated_tokens": usage.get("completion_tokens", timings.get("predicted_n")),
            "prefill_tokens_per_second": timings.get("prompt_per_second"),
            "generation_tokens_per_second": timings.get("predicted_per_second")}
        self.save_state("ready")

    def proxy(self, handler: BaseHTTPRequestHandler, profile: dict[str, Any], body: bytes, upstream_path: str | None = None) -> None:
        connection = http.client.HTTPConnection("127.0.0.1", int(profile["port"]), timeout=900)
        connection.request(handler.command, upstream_path or handler.path, body, {"Content-Type": "application/json", "Accept": handler.headers.get("Accept", "application/json")})
        response = connection.getresponse(); content_type = response.getheader("Content-Type", "application/json")
        streaming = b'"stream": true' in body
        handler.send_response(response.status); handler.send_header("Content-Type", content_type)
        handler.send_header("Access-Control-Allow-Origin", "*")
        if streaming:
            handler.send_header("Transfer-Encoding", "chunked"); handler.end_headers()
            while chunk := response.read(65536):
                handler.wfile.write(f"{len(chunk):X}\r\n".encode() + chunk + b"\r\n"); handler.wfile.flush()
            handler.wfile.write(b"0\r\n\r\n")
        else:
            payload = response.read()
            if 200 <= response.status < 300:
                try: self.record_generation(json.loads(payload))
                except (UnicodeDecodeError, json.JSONDecodeError): pass
            handler.send_header("Content-Length", str(len(payload))); handler.end_headers(); handler.wfile.write(payload)
        connection.close()


def serve(config: Path, state: Path) -> None:
    gateway = Gateway(config, state)
    gateway.save_state("idle", "gateway started; no backend loaded")
    host, port = gateway.config["gateway"]["host"], int(gateway.config["gateway"]["port"])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: Any) -> None: pass
        def reply(self, code: int, value: dict[str, Any]) -> None:
            body = json.dumps(value).encode(); self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body)
        def api_authorized(self) -> bool:
            return self.headers.get("Authorization") == "Bearer " + gateway.api_token
        @staticmethod
        def catalog() -> dict[str, Any]:
            return {"object": "list", "data": [{"id": name, "object": "model", "owned_by": "local", "ready": profile.get("admitted", False)} for name, profile in gateway.models.items()]}
        def do_OPTIONS(self) -> None:
            self.send_response(204); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization"); self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS"); self.end_headers()
        def do_GET(self) -> None:
            if self.path == "/":
                body = UI.read_bytes(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body); return
            if self.path == "/health": self.reply(200, {"status": "ok", "active_model": gateway.active}); return
            if self.path == "/ui/models": self.reply(200, self.catalog()); return
            if self.path in {"/ui/status", "/v1/host/status"}:
                if self.path.startswith("/v1/") and not self.api_authorized(): self.reply(401, {"error": {"message": "API authentication required"}}); return
                self.reply(200, gateway.status("ready" if gateway.active else "idle"))
                return
            if self.path == "/v1/models":
                if not self.api_authorized(): self.reply(401, {"error": {"message": "API authentication required"}}); return
                self.reply(200, self.catalog()); return
            self.reply(404, {"error": {"message": "not found"}})
        def do_POST(self) -> None:
            ui_request = self.path == "/ui/chat"
            if not ui_request and self.path not in {"/v1/chat/completions", "/v1/completions", "/v1/responses"}: self.reply(404, {"error": {"message": "not found"}}); return
            if not ui_request and not self.api_authorized(): self.reply(401, {"error": {"message": "API authentication required"}}); return
            if not gateway.lock.acquire(blocking=False):
                self.reply(429, {"error": {"message": "model is busy; retry after the active request completes", "type": "model_busy"}})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16 * 1024 * 1024: raise ValueError("invalid request size")
                body = self.rfile.read(length); request = json.loads(body); runtime = request.pop("runtime", {}) if ui_request else {}
                profile = gateway.activate(request.get("model", ""), runtime)
                request["model"] = "local"
                gateway.proxy(self, profile, json.dumps(request).encode(), "/v1/chat/completions" if ui_request else None)
            except PermissionError as exc: self.reply(409, {"error": {"message": str(exc), "type": "model_not_admitted"}})
            except (ValueError, json.JSONDecodeError) as exc: self.reply(400, {"error": {"message": str(exc), "type": "invalid_request_error"}})
            except (OSError, RuntimeError) as exc: self.reply(503, {"error": {"message": str(exc), "type": "service_unavailable"}})
            finally: gateway.lock.release()
    try: ThreadingHTTPServer((host, port), Handler).serve_forever()
    finally: gateway.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--config", type=Path, required=True); parser.add_argument("--state", type=Path, required=True)
    options = parser.parse_args(); serve(options.config, options.state)
