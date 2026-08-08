#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import json
import os
import pathlib
import time
import urllib.parse


def key_from(path: pathlib.Path) -> str:
    info = path.lstat()
    if path.is_symlink() or info.st_mode & 0o037:
        raise ValueError("key file permissions are too broad")
    return path.read_text(encoding="utf-8").splitlines()[0]


def request(port: int, path: str, key: str, model: str) -> dict:
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": "Reply only OK"}],
                       "max_tokens": 8, "temperature": 0, "stream": False}).encode()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1800)
    started = time.monotonic()
    try:
        connection.request("POST", path, body=body,
                           headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        response = connection.getresponse()
        payload = response.read(1024 * 1024)
        return {"model": model, "status": response.status, "ok": 200 <= response.status < 300 and b"OK" in payload,
                "duration_ms": round((time.monotonic() - started) * 1000, 3)}
    except OSError as exc:
        return {"model": model, "status": None, "ok": False, "error": type(exc).__name__}
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080/v1/chat/completions")
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--flash-model", default="flash-q2")
    parser.add_argument("--fast-model", required=True)
    parser.add_argument("--duration-seconds", type=int, default=14400)
    parser.add_argument("--interval-seconds", type=float, default=60)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("soak endpoint must be loopback HTTP")
    if args.duration_seconds < 1 or args.interval_seconds <= 0:
        parser.error("invalid duration or interval")
    key = key_from(pathlib.Path(args.key_file))
    deadline = time.monotonic() + args.duration_seconds
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        while time.monotonic() < deadline:
            futures = [executor.submit(request, parsed.port or 8080, parsed.path, key, model)
                       for model in (args.flash_model, args.fast_model)]
            results.extend(future.result() for future in futures)
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval_seconds, remaining))
    report = {"schema": 1, "duration_seconds": args.duration_seconds,
              "requests": len(results), "passed": sum(item["ok"] for item in results), "results": results}
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}")
    temporary.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    return 0 if report["passed"] == report["requests"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
