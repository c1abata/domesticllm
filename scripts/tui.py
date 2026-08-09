#!/usr/bin/env python3
"""Small local terminal client for cpu-inference's OpenAI-compatible API."""

import argparse
import json
import sys
import urllib.error
import urllib.request


def complete(base_url: str, model: str, messages: list[dict[str, str]]) -> str:
    body = json.dumps({"model": model, "messages": messages}).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.load(response)
    return payload["choices"][0]["message"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Local CPU Inference TUI")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument(
        "--model",
        default="/srv/local-ai/models/Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf",
    )
    args = parser.parse_args()
    messages: list[dict[str, str]] = []
    print("CPU Inference TUI — /clear clears history; /exit quits.")

    while True:
        try:
            prompt = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not prompt:
            continue
        if prompt == "/exit":
            return 0
        if prompt == "/clear":
            messages.clear()
            print("history cleared")
            continue
        messages.append({"role": "user", "content": prompt})
        try:
            answer = complete(args.base_url, args.model, messages)
        except (KeyError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            messages.pop()
            print(f"request failed: {error}", file=sys.stderr)
            continue
        messages.append({"role": "assistant", "content": answer})
        print(f"assistant> {answer}")


if __name__ == "__main__":
    raise SystemExit(main())
