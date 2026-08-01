#!/usr/bin/env python3
"""Dependency-free DS4 streaming status UI for DomesticLLM."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import queue
import shutil
import signal
import sys
import textwrap
import threading
import time
import urllib.parse

DEFAULT_URL = "http://127.0.0.1:8083/v1/chat/completions"
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("deve essere maggiore di zero")
    return number


def validate_url(value: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("l'URL deve essere assoluto e usare http o https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("credenziali, query e fragment non sono ammessi nell'URL")
    return parsed


def load_key() -> str | None:
    key = os.environ.get("LOCAL_AI_API_KEY")
    path = os.environ.get("LOCAL_AI_API_KEY_FILE")
    if not key and path:
        info = os.lstat(path)
        if os.path.islink(path) or info.st_mode & 0o037:
            raise ValueError("il file API key non deve essere un symlink e richiede permessi 0640 o più stretti")
        with open(path, encoding="utf-8") as source:
            key = source.readline().rstrip("\r\n")
    if key and (any(c in key for c in "\r\n") or not all(c.isalnum() or c in "._~+/=-" for c in key)):
        raise ValueError("API key con caratteri non supportati")
    return key or None


def terminal_safe(value: str) -> str:
    """Keep readable text while removing terminal control sequences."""
    return "".join(char for char in value if char in "\n\t" or ord(char) >= 32 and ord(char) != 127)


def request_worker(url: str, payload: dict, key: str | None, events: queue.Queue, holder: dict) -> None:
    parsed = validate_url(url)
    cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    connection = cls(parsed.hostname, port, timeout=1800)
    holder["connection"] = connection
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        events.put(("connecting", time.monotonic(), None))
        connection.request("POST", parsed.path or "/", json.dumps(payload).encode(), headers)
        events.put(("submitted", time.monotonic(), None))
        response = connection.getresponse()
        events.put(("headers", time.monotonic(), response.status))
        if not 200 <= response.status < 300:
            body = response.read(8192).decode("utf-8", "replace")
            raise RuntimeError(f"HTTP {response.status}: {body}")
        while True:
            line = response.readline()
            if not line:
                break
            if not line.startswith(b"data:"):
                continue
            raw = line[5:].strip()
            if not raw:
                continue
            if raw == b"[DONE]":
                events.put(("done", time.monotonic(), None))
                return
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                events.put(("malformed", time.monotonic(), raw[:160].decode("utf-8", "replace")))
                continue
            if event.get("usage"):
                events.put(("usage", time.monotonic(), event["usage"]))
            choices = event.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                content = delta.get("content") or ""
                if reasoning:
                    events.put(("reasoning", time.monotonic(), reasoning))
                if content:
                    events.put(("content", time.monotonic(), content))
                finish = choices[0].get("finish_reason")
                if finish:
                    events.put(("finish", time.monotonic(), finish))
        events.put(("done", time.monotonic(), None))
    except Exception as exc:  # reported in the UI, never silently swallowed
        events.put(("error", time.monotonic(), str(exc)))
    finally:
        connection.close()


def clipped_lines(text: str, width: int, height: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, max(width, 10), replace_whitespace=False) or [""])
    return lines[-height:]


def render(state: dict, interactive: bool) -> None:
    now = time.monotonic()
    elapsed = now - state["started"]
    since_event = now - state["last_event"]
    phase = state["phase"]
    if phase not in {"COMPLETATO", "ERRORE"} and since_event >= state["stall"]:
        phase = "POSSIBILE STALLO"
    elif phase in {"PREFILL", "IN CODA / PREFILL"} and since_event >= state["slow"]:
        phase = "DS4 ATTIVO · CODA/PREFILL/THINKING"
    glyph = "✓" if phase == "COMPLETATO" else "✗" if phase == "ERRORE" else SPINNER[int(elapsed * 8) % len(SPINNER)]
    usage = state["usage"]
    prompt_tokens = usage.get("prompt_tokens") or state["prompt_estimate"]
    completion_tokens = usage.get("completion_tokens") or state["delta_events"]
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    context = state["context"]
    percent = min(100.0, 100 * (prompt_tokens + completion_tokens) / context)
    ttft = state.get("ttft")
    decode_elapsed = max(now - state["first_token"], 0.001) if state.get("first_token") else 0
    rate = completion_tokens / decode_elapsed if decode_elapsed else 0
    width, height = shutil.get_terminal_size((100, 30))
    width = max(60, min(width, 140))
    bar_width = max(12, width - 50)
    filled = round(bar_width * percent / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    lines = [
        f" DomesticLLM · DS4 Flash   {glyph} {phase}",
        "─" * width,
        f" sessione  {state['session']}   modello  {state['model']}",
        f" endpoint  {state['url']}   HTTP  {state.get('http_status') or '—'}",
        f" tempo     {elapsed:7.1f}s   ultimo evento {since_event:6.1f}s   TTFT {ttft:.2f}s" if ttft else
        f" tempo     {elapsed:7.1f}s   ultimo evento {since_event:6.1f}s   TTFT in attesa",
        f" contesto  [{bar}] {prompt_tokens + completion_tokens}/{context} ({percent:.2f}%)",
        f" token     prompt≈{prompt_tokens}  cache={cached}  output={completion_tokens}  decode≈{rate:.2f} tok/s",
        f" eventi    SSE={state['sse_events']}  delta={state['delta_events']}  malformed={state['malformed']}",
        "─" * width,
        " Risposta (ultime righe)",
    ]
    preview = state["content"] or ("[ragionamento in corso]\n" + state["reasoning"] if state["reasoning"] else "In attesa del primo token…")
    preview = terminal_safe(preview)
    lines.extend(" " + line for line in clipped_lines(preview, width - 2, max(4, height - len(lines) - 3)))
    lines.extend(["─" * width, " Ctrl-C annulla · il watchdog segnala lo stallo ma non interrompe il modello"])
    screen = "\n".join(line[:width] for line in lines)
    if interactive:
        sys.stderr.write("\x1b[H\x1b[2J" + screen)
        sys.stderr.flush()
    elif now - state.get("last_plain_render", 0) >= 5 or phase in {"COMPLETATO", "ERRORE"}:
        sys.stderr.write(f"[{elapsed:6.1f}s] {phase}; ultimo evento {since_event:.1f}s; output≈{completion_tokens}; {rate:.2f} tok/s\n")
        sys.stderr.flush()
        state["last_plain_render"] = now


def main() -> int:
    parser = argparse.ArgumentParser(description="TUI streaming per DomesticLLM/DS4")
    parser.add_argument("prompt", nargs="*", help="domanda; se omessa viene letta da stdin")
    parser.add_argument("--url", default=os.environ.get("DOMESTICLLM_URL", DEFAULT_URL))
    parser.add_argument("--model", default=os.environ.get("DOMESTICLLM_MODEL", "deepseek-v4-flash"))
    parser.add_argument("--max-tokens", type=positive_int, default=positive_int(os.environ.get("DOMESTICLLM_MAX_TOKENS", "512")))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("DOMESTICLLM_TEMPERATURE", "0.15")))
    parser.add_argument("--context", type=positive_int, default=positive_int(os.environ.get("DOMESTICLLM_CONTEXT", "100000")))
    parser.add_argument("--show-reasoning", action="store_true", default=os.environ.get("DOMESTICLLM_SHOW_REASONING") == "1")
    args = parser.parse_args()
    try:
        validate_url(args.url)
        key = load_key()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    prompt = " ".join(args.prompt) if args.prompt else (sys.stdin.read() if not sys.stdin.isatty() else "")
    if not prompt.strip():
        parser.error("fornire un prompt come argomento o tramite stdin")
    payload = {"model": args.model, "messages": [{"role": "user", "content": prompt}],
               "max_tokens": args.max_tokens, "max_completion_tokens": args.max_tokens,
               "temperature": args.temperature,
               "stream": True, "stream_options": {"include_usage": True}}
    started = time.monotonic()
    state = {"started": started, "last_event": started, "phase": "CONNESSIONE", "url": args.url,
             "model": args.model, "session": f"{int(time.time()):x}-{os.getpid():x}", "context": args.context,
             "prompt_estimate": max(1, len(prompt) // 4), "usage": {}, "content": "", "reasoning": "",
             "sse_events": 0, "delta_events": 0, "malformed": 0,
             "slow": float(os.environ.get("DOMESTICLLM_SLOW_SECONDS", "45")),
             "stall": float(os.environ.get("DOMESTICLLM_STALL_SECONDS", "600"))}
    events: queue.Queue = queue.Queue()
    holder: dict = {}
    worker = threading.Thread(target=request_worker, args=(args.url, payload, key, events, holder), daemon=True)
    interactive = sys.stderr.isatty()
    if interactive:
        sys.stderr.write("\x1b[?1049h\x1b[?25l")
    worker.start()
    error = None
    try:
        finished = False
        while not finished:
            try:
                kind, at, data = events.get(timeout=0.125)
                state["last_event"] = at
                if kind != "connecting":
                    state["sse_events"] += 1
                if kind == "submitted":
                    state["phase"] = "IN CODA / PREFILL"
                elif kind == "headers":
                    state.update(phase="PREFILL", http_status=data)
                elif kind in {"reasoning", "content"}:
                    if "first_token" not in state:
                        state["first_token"] = at
                        state["ttft"] = at - started
                    state["phase"] = "GENERAZIONE"
                    state[kind] += data
                    state["delta_events"] += 1
                elif kind == "usage":
                    state["usage"] = data
                elif kind == "malformed":
                    state["malformed"] += 1
                elif kind == "finish":
                    state["finish_reason"] = data
                elif kind == "error":
                    state["phase"], error, finished = "ERRORE", data, True
                elif kind == "done":
                    state["phase"], finished = "COMPLETATO", True
            except queue.Empty:
                pass
            render(state, interactive)
    except KeyboardInterrupt:
        connection = holder.get("connection")
        if connection:
            connection.close()
        state["phase"], error = "ERRORE", "annullato dall'operatore"
        render(state, interactive)
    finally:
        if interactive:
            time.sleep(0.4)
            sys.stderr.write("\x1b[?25h\x1b[?1049l")
            sys.stderr.flush()
    if error:
        print(f"Errore: {terminal_safe(error)}", file=sys.stderr)
        return 1
    answer = state["content"] or state["reasoning"]
    if args.show_reasoning and state["reasoning"] and state["content"]:
        answer = state["reasoning"] + "\n\n" + state["content"]
    if not answer:
        print("Errore: stream completato senza contenuto", file=sys.stderr)
        return 1
    print(terminal_safe(answer) if sys.stdout.isatty() else answer)
    usage = state["usage"]
    print(f"[DS4] completato in {time.monotonic()-started:.1f}s; prompt={usage.get('prompt_tokens', '?')}; "
          f"output={usage.get('completion_tokens', state['delta_events'])}; finish={state.get('finish_reason', '?')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
