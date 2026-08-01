#!/usr/bin/env python3
"""Narrow stdio MCP server for local repository and inference operations."""

from __future__ import annotations

import ipaddress
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from mcp.server.fastmcp import FastMCP

if version("mcp") != "1.28.1":
    raise RuntimeError("local-ai MCP requires exactly mcp==1.28.1")


SERVER = FastMCP(
    "local-ai",
    instructions="Repository reads, fixed checks, loopback inference, and redacted logs only.",
    log_level="WARNING",
)
REPO_ROOT = Path(os.environ.get("LOCAL_AI_REPO_ROOT", Path(__file__).resolve().parents[1])).resolve()
MAX_READ = 64 * 1024
MAX_SEARCH_FILE = 1024 * 1024
MAX_OUTPUT = 256 * 1024
DENIED_PARTS = {".git", ".gnupg", ".ssh", ".aws", ".azure", ".config", ".kube", "secrets"}
DENIED_FILE_RE = re.compile(
    r"(^\.env(?:\..*)?$|(?:^|[-_.])(secret|token|password|credential|private[-_]?key)(?:[-_.]|$)|\.(?:key|pem|p12|pfx)$)",
    re.I,
)
TEXT_SUFFIXES = {
    "", ".c", ".cc", ".cpp", ".h", ".json", ".md", ".ps1", ".py",
    ".service", ".sh", ".toml", ".txt", ".yaml", ".yml",
}
BACKENDS = {
    "ds4": ("LOCAL_AI_DS4_URL", "http://127.0.0.1:8083"),
    "llama": ("LOCAL_AI_LLAMA_URL", "http://127.0.0.1:8082"),
}
LOG_UNITS = {
    "ds4-canary": "local-ai-ds4-native.service",
    "ds4-primary": "local-ai-ds4-native.service",
    "llama-primary": "local-ai-ds4-nvidia.service",
    "llama-fallback": "local-ai-llama-fallback.service",
}
CHECKS = {
    "mcp-tests": (sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_mcp*.py"),
    "client-tests": (sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_client*.py"),
    "policy-tests": (sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_policy.py"),
    "runtime-tests": ("bash", "tests/test_ds4_runtime.sh"),
    "git-diff-check": ("git", "diff", "--check", "--"),
}


def _result(ok: bool, summary: str, evidence: list[Any] | None = None,
            artifacts: list[str] | None = None, next_gate: str = "PLAN") -> dict[str, Any]:
    return {"ok": ok, "summary": summary, "evidence": evidence or [],
            "artifacts": artifacts or [], "next_gate": next_gate}


def _failure(exc: Exception, next_gate: str = "HUMAN_GATE") -> dict[str, Any]:
    return _result(False, str(exc), next_gate=next_gate)


def _is_sensitive(relative: Path) -> bool:
    return (any(part.casefold() in DENIED_PARTS for part in relative.parts)
            or bool(DENIED_FILE_RE.search(relative.name)))


def _confined_path(user_path: str) -> Path:
    if not user_path or "\x00" in user_path:
        raise ValueError("path is empty or invalid")
    relative = Path(user_path)
    if relative.is_absolute():
        raise ValueError("absolute paths are not allowed")
    candidate = (REPO_ROOT / relative).resolve(strict=True)
    try:
        confined = candidate.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError("path escapes the repository") from exc
    if _is_sensitive(confined):
        raise ValueError("sensitive paths are not exposed")
    return candidate


def _safe_env() -> dict[str, str]:
    env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR") if key in os.environ}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_OPTIONAL_LOCKS": "0", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1", "SYSTEMD_COLORS": "0"})
    return env


SENSITIVE_LOG_RE = re.compile(
    r"(?i)(authorization|bearer|api[-_ ]?key|password|passwd|secret|credential|"
    r"private[-_ ]?key|prompt|messages?|completion|response|content|input|tokens?)"
)


def _redact(text: str, limit: int = 512 * 1024) -> str:
    lines = []
    redacting_continuation = False
    journal_start = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
    for line in text[:limit].splitlines():
        if journal_start.search(line):
            redacting_continuation = False
        if redacting_continuation or SENSITIVE_LOG_RE.search(line):
            lines.append("[REDACTED sensitive log entry]")
            redacting_continuation = True
        else:
            lines.append(line)
    if len(text) > limit:
        lines.append("[TRUNCATED]")
    return "\n".join(lines)


def _run_fixed(command: tuple[str, ...], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=REPO_ROOT, env=_safe_env(), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, shell=False, check=False,
    )


def _backend_url(backend: str) -> str:
    try:
        env_name, default = BACKENDS[backend]
    except KeyError as exc:
        raise ValueError(f"backend must be one of: {', '.join(BACKENDS)}") from exc
    url = os.environ.get(env_name, default).rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.username or parsed.password:
        raise ValueError("inference URL must be unauthenticated loopback HTTP")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError("inference URL must not include a path, query, or fragment")
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError as exc:
        raise ValueError("inference URL must use a loopback IP literal") from exc
    if not address.is_loopback or parsed.port not in (8082, 8083, 8084):
        raise ValueError("inference URL must use loopback port 8082, 8083, or 8084")
    return url


def _json_request(backend: str, path: str, payload: dict[str, Any] | None = None,
                  timeout: int = 30) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(_backend_url(backend) + path, data=data,
                      method="GET" if data is None else "POST",
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310; loopback validated above.
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise RuntimeError("inference response exceeds size limit")
            body = json.loads(raw.decode()) if raw else {}
            if not isinstance(body, dict):
                raise RuntimeError("inference response is not a JSON object")
            return response.status, body
    except HTTPError as exc:
        raise RuntimeError(f"inference returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"inference unavailable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("inference returned invalid JSON") from exc


def _model_id(backend: str) -> tuple[str, int]:
    status, body = _json_request(backend, "/v1/models", timeout=10)
    models = body.get("data")
    if status != 200 or not isinstance(models, list) or not models:
        raise RuntimeError("/v1/models did not return at least one model")
    first = models[0]
    if not isinstance(first, dict) or not isinstance(first.get("id"), str):
        raise RuntimeError("/v1/models returned an invalid model entry")
    return first["id"], len(models)


@SERVER.tool(description="List non-sensitive repository files.")
def repo_inventory(path: str = ".", max_entries: int = 500) -> dict[str, Any]:
    try:
        if not 1 <= max_entries <= 1000:
            raise ValueError("max_entries must be between 1 and 1000")
        base = _confined_path(path)
        if not base.is_dir():
            raise ValueError("path is not a directory")
        entries: list[dict[str, Any]] = []
        for current, dirs, files in os.walk(base, followlinks=False):
            current_path = Path(current)
            dirs[:] = sorted(name for name in dirs
                             if not _is_sensitive((current_path / name).relative_to(REPO_ROOT)))
            for name in sorted(files):
                candidate = current_path / name
                relative = candidate.relative_to(REPO_ROOT)
                if _is_sensitive(relative) or candidate.is_symlink():
                    continue
                entries.append({"path": relative.as_posix(), "size": candidate.stat().st_size})
                if len(entries) >= max_entries:
                    return _result(True, f"{len(entries)} files (truncated)", entries)
        return _result(True, f"{len(entries)} files", entries)
    except (OSError, ValueError) as exc:
        return _failure(exc)


@SERVER.tool(description="Read one bounded, non-sensitive repository text file.")
def repo_read(path: str) -> dict[str, Any]:
    try:
        candidate = _confined_path(path)
        if not candidate.is_file() or candidate.is_symlink():
            raise ValueError("path is not a regular file")
        if candidate.suffix.casefold() not in TEXT_SUFFIXES:
            raise ValueError("file type is not exposed")
        raw = candidate.read_bytes()
        if len(raw) > MAX_READ:
            raise ValueError(f"file exceeds {MAX_READ} byte limit")
        if b"\x00" in raw:
            raise ValueError("binary files are not exposed")
        content = raw.decode("utf-8")
        relative = candidate.relative_to(REPO_ROOT).as_posix()
        return _result(True, f"read {relative}", [{"path": relative, "content": content}])
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return _failure(exc)


@SERVER.tool(description="Literal text search over bounded repository files.")
def repo_search(query: str, path: str = ".", case_sensitive: bool = False,
                max_results: int = 100) -> dict[str, Any]:
    try:
        if not query or len(query) > 256 or "\x00" in query:
            raise ValueError("query must contain 1 to 256 text characters")
        if not 1 <= max_results <= 200:
            raise ValueError("max_results must be between 1 and 200")
        base = _confined_path(path)
        if not base.is_dir():
            raise ValueError("path is not a directory")
        needle = query if case_sensitive else query.casefold()
        matches: list[dict[str, Any]] = []
        for current, dirs, files in os.walk(base, followlinks=False):
            current_path = Path(current)
            dirs[:] = sorted(name for name in dirs
                             if not _is_sensitive((current_path / name).relative_to(REPO_ROOT)))
            for name in sorted(files):
                candidate = current_path / name
                relative = candidate.relative_to(REPO_ROOT)
                if (_is_sensitive(relative) or candidate.is_symlink()
                        or candidate.suffix.casefold() not in TEXT_SUFFIXES
                        or candidate.stat().st_size > MAX_SEARCH_FILE):
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                for number, line in enumerate(text.splitlines(), 1):
                    if needle in (line if case_sensitive else line.casefold()):
                        matches.append({"path": relative.as_posix(), "line": number, "text": line[:500]})
                        if len(matches) >= max_results:
                            return _result(True, f"{len(matches)} matches (truncated)", matches)
        return _result(True, f"{len(matches)} matches", matches)
    except (OSError, ValueError) as exc:
        return _failure(exc)


@SERVER.tool(description="Show a bounded Git working-tree or staged diff.")
def repo_diff(staged: bool = False) -> dict[str, Any]:
    command = ["git", "-c", "core.pager=cat", "diff", "--no-ext-diff", "--no-textconv"]
    if staged:
        command.append("--cached")
    command.append("--")
    try:
        done = _run_fixed(tuple(command), 30)
        output = _redact(done.stdout[:MAX_OUTPUT], MAX_OUTPUT)
        evidence: list[Any] = [{"diff": output}]
        if done.stderr:
            evidence.append({"stderr": _redact(done.stderr, 4096)})
        ok = done.returncode == 0
        return _result(ok, "git diff complete" if ok else f"git diff exited {done.returncode}",
                       evidence, next_gate="PLAN" if ok else "HUMAN_GATE")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _failure(exc)


@SERVER.tool(description="Run one fixed verification check from the allowlist.")
def check_run(check_id: str) -> dict[str, Any]:
    if check_id not in CHECKS:
        return _failure(ValueError(f"unknown check_id; allowed: {', '.join(CHECKS)}"))
    try:
        done = _run_fixed(CHECKS[check_id], 180)
        evidence: list[Any] = [{"check_id": check_id, "exit_code": done.returncode}]
        if done.stdout:
            evidence.append({"stdout": _redact(done.stdout, MAX_OUTPUT)})
        if done.stderr:
            evidence.append({"stderr": _redact(done.stderr, 16 * 1024)})
        ok = done.returncode == 0
        return _result(ok, f"{check_id} {'passed' if ok else 'failed'}", evidence,
                       next_gate="SECURITY_REVIEW" if ok else "HUMAN_GATE")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _failure(exc)


@SERVER.tool(description="Check one configured loopback inference backend.")
def inference_health(backend: str = "ds4") -> dict[str, Any]:
    try:
        started = time.monotonic()
        model, count = _model_id(backend)
        return _result(True, f"{backend} is healthy", [{"backend": backend, "model": model,
            "model_count": count, "latency_ms": round((time.monotonic() - started) * 1000, 2)}],
            next_gate="VERIFY")
    except (RuntimeError, ValueError) as exc:
        return _failure(exc)


def _complete(backend: str, model: str, timeout: int) -> tuple[float, dict[str, Any]]:
    payload = {"model": model, "messages": [{"role": "user", "content": "Reply with exactly OK."}],
               "temperature": 0, "max_tokens": 8, "stream": False}
    started = time.monotonic()
    status, body = _json_request(backend, "/v1/chat/completions", payload, timeout)
    elapsed = time.monotonic() - started
    if status != 200 or not isinstance(body.get("choices"), list) or not body["choices"]:
        raise RuntimeError("chat completion contract failed")
    return elapsed, body


@SERVER.tool(description="Run one deterministic loopback inference smoke request.")
def inference_smoke(backend: str = "ds4") -> dict[str, Any]:
    try:
        model, _ = _model_id(backend)
        elapsed, body = _complete(backend, model, 120)
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        return _result(True, f"{backend} smoke passed", [{"backend": backend, "model": model,
            "latency_ms": round(elapsed * 1000, 2), "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens")}], next_gate="VERIFY")
    except (RuntimeError, ValueError) as exc:
        return _failure(exc)


@SERVER.tool(description="Run a bounded sequential loopback micro-benchmark.")
def inference_benchmark(backend: str = "ds4", iterations: int = 3) -> dict[str, Any]:
    try:
        if not 1 <= iterations <= 5:
            raise ValueError("iterations must be between 1 and 5")
        model, _ = _model_id(backend)
        latencies, tokens = [], 0
        for _ in range(iterations):
            elapsed, body = _complete(backend, model, 180)
            latencies.append(elapsed)
            usage = body.get("usage")
            if isinstance(usage, dict) and isinstance(usage.get("completion_tokens"), int):
                tokens += usage["completion_tokens"]
        total = sum(latencies)
        evidence = {"backend": backend, "model": model, "iterations": iterations,
            "mean_latency_ms": round(total * 1000 / iterations, 2),
            "min_latency_ms": round(min(latencies) * 1000, 2),
            "max_latency_ms": round(max(latencies) * 1000, 2),
            "completion_tokens_per_second": round(tokens / total, 2) if tokens and total else None,
            "scope": "micro-benchmark; not the acceptance suite"}
        return _result(True, f"{backend} micro-benchmark complete", [evidence], next_gate="VERIFY")
    except (RuntimeError, ValueError) as exc:
        return _failure(exc)


@SERVER.tool(description="Read bounded, redacted journal lines for one allowlisted unit.")
def ops_logs(unit: str, lines: int = 200) -> dict[str, Any]:
    if unit not in LOG_UNITS:
        return _failure(ValueError(f"unit must be one of: {', '.join(LOG_UNITS)}"))
    if not 1 <= lines <= 500:
        return _failure(ValueError("lines must be between 1 and 500"))
    command = ("journalctl", "--no-pager", "--output=short-iso", "--unit", LOG_UNITS[unit],
               "--lines", str(lines))
    try:
        done = _run_fixed(command, 30)
        evidence: list[Any] = [{"unit": LOG_UNITS[unit], "logs": _redact(done.stdout)}]
        if done.stderr:
            evidence.append({"stderr": _redact(done.stderr, 4096)})
        ok = done.returncode == 0
        return _result(ok, f"logs for {unit} {'collected' if ok else 'failed'}", evidence,
                       next_gate="SECURITY_REVIEW" if ok else "HUMAN_GATE")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _failure(exc)


def main() -> None:
    if not REPO_ROOT.is_dir():
        raise SystemExit("LOCAL_AI_REPO_ROOT is not a repository directory")
    SERVER.run(transport="stdio")


if __name__ == "__main__":
    main()
