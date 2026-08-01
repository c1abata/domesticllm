#!/usr/bin/env python3
"""Bounded DS4 hardware soak with machine-readable evidence."""

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def post(url, payload, timeout=1200):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
        status = response.status
    return status, body, time.monotonic() - started


def gpu_snapshot():
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.used,utilization.gpu,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        timeout=15,
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=14400)
    parser.add_argument("--interval-seconds", type=int, default=45)
    parser.add_argument("--url", default="http://127.0.0.1:8083/v1/chat/completions")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.interval_seconds < 0:
        raise SystemExit("duration must be positive and interval non-negative")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.duration_seconds
    iteration = 0
    failures = 0
    with args.output.open("a", encoding="utf-8", buffering=1) as evidence:
        while time.monotonic() < deadline:
            iteration += 1
            kind = "short"
            payload = {
                "model": "deepseek-v4-flash",
                "messages": [{"role": "user", "content": "Rispondi con una frase: sistema operativo."}],
                "temperature": 0,
                "max_tokens": 32,
            }
            if iteration % 20 == 0:
                kind = "kv-long"
                payload["messages"][0]["content"] = "alpha " * 2600 + "\nRispondi READY."
                payload["max_tokens"] = 1
            elif iteration % 10 == 0:
                kind = "tool"
                payload.update(
                    {
                        "messages": [{"role": "user", "content": "Usa meteo per Roma."}],
                        "tools": [{
                            "type": "function",
                            "function": {
                                "name": "meteo",
                                "description": "Ottiene il meteo",
                                "parameters": {
                                    "type": "object",
                                    "properties": {"citta": {"type": "string"}},
                                    "required": ["citta"],
                                },
                            },
                        }],
                        "tool_choice": "required",
                        "max_tokens": 96,
                    }
                )
            record = {"iteration": iteration, "kind": kind, "started_unix": time.time()}
            try:
                status, body, elapsed = post(args.url, payload)
                choice = (body.get("choices") or [{}])[0]
                record.update(
                    status=status,
                    elapsed_seconds=elapsed,
                    finish_reason=choice.get("finish_reason"),
                    usage=body.get("usage"),
                    gpu=gpu_snapshot(),
                )
                if status != 200 or not body.get("choices"):
                    raise RuntimeError("invalid completion response")
                if kind == "tool":
                    calls = (choice.get("message") or {}).get("tool_calls") or []
                    if len(calls) != 1 or calls[0].get("function", {}).get("name") != "meteo":
                        raise RuntimeError("tool calling validation failed")
            except Exception as error:  # evidence must survive every failure type
                failures += 1
                record.update(error=type(error).__name__ + ": " + str(error), gpu=gpu_snapshot())
                evidence.write(json.dumps(record, sort_keys=True) + "\n")
                raise
            evidence.write(json.dumps(record, sort_keys=True) + "\n")
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval_seconds, remaining))
    summary = {"iterations": iteration, "failures": failures, "duration_seconds": args.duration_seconds}
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
