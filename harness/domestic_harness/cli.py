from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .client import InferenceError
from .config import ConfigError, load_config
from .harness import DomesticHarness


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="domestic-harness")
    parser.add_argument("--config", type=Path, default=Path("~/.config/domesticllm/harness.toml").expanduser())
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="send one request")
    ask.add_argument("prompt", nargs="+")
    ask.add_argument("--profile")
    ask.add_argument("--session", default="default")
    ask.add_argument("--no-memory", action="store_true")
    ask.add_argument("--meta", action="store_true", help="print routing and timing on stderr")

    check = sub.add_parser("check", help="verify server health and model discovery")
    check.add_argument("--profile")

    clear = sub.add_parser("clear", help="delete one local conversation")
    clear.add_argument("--session", default="default")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        harness = DomesticHarness(load_config(args.config))
        try:
            if args.command == "ask":
                result = harness.ask(
                    " ".join(args.prompt),
                    session=args.session,
                    profile_name=args.profile,
                    remember=not args.no_memory,
                )
                print(result.inference.content)
                if args.meta:
                    print(
                        f"profile={result.route.profile.name} task={result.route.task} "
                        f"reason={result.route.reason} elapsed={result.inference.elapsed_seconds:.3f}s "
                        f"prompt_tokens={result.inference.prompt_tokens} "
                        f"completion_tokens={result.inference.completion_tokens}",
                        file=sys.stderr,
                    )
            elif args.command == "check":
                for name, models in harness.check(args.profile).items():
                    print(f"{name}: ok; models={','.join(models) if models else '(none reported)'}")
            elif args.command == "clear":
                harness.store.clear(args.session)
                print(f"cleared session: {args.session}")
        finally:
            harness.close()
    except (ConfigError, InferenceError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
