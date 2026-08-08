from __future__ import annotations

import argparse
import json
import pathlib
import sys
import subprocess
import urllib.parse
import urllib.request

from .common import Paths, PDS4Error, read_json, sha256_file
from .gpu import assign as assign_gpus, discover as discover_gpus
from .doctor import inspect as doctor_inspect
from .lane import flash_action, read_lane_state, switch_fast
from .bundle import create as bundle_create, import_bundle, recover as bundle_recover, verify as bundle_verify
from .cache import (checkpoint as cache_checkpoint, inspect as cache_inspect,
                    list_checkpoints, parse_size, prune as cache_prune,
                    restore as cache_restore, verify_checkpoint)
from .benchmark import hardware_snapshot, plan as benchmark_plan, record as benchmark_record, run_request
from .manifest import validate_manifest
from .store import import_model, inspect_gguf, verify_installed


def command_model(args: argparse.Namespace, paths: Paths) -> int:
    if args.model_command == "verify":
        print(json.dumps(verify_installed(args.model_id, paths), indent=2, sort_keys=True))
        return 0
    if args.model_command == "inspect":
        print(json.dumps(validate_manifest(read_json(pathlib.Path(args.manifest))), indent=2, sort_keys=True))
        return 0
    if args.model_command == "import":
        manifest = import_model(pathlib.Path(args.manifest), pathlib.Path(args.artifacts), paths)
        print(f"verified {manifest['id']}")
        return 0
    if args.model_command == "list":
        if not paths.models.exists():
            return 0
        for manifest_path in sorted(paths.models.glob("*/manifest.json")):
            manifest = validate_manifest(read_json(manifest_path))
            print(f"{manifest['id']}\t{manifest['status']}\t{manifest['lane']}")
        return 0
    if args.model_command == "fetch":
        if os.geteuid() == 0:
            raise PDS4Error("model fetch must run as an unprivileged user")
        manifest_path = pathlib.Path(args.manifest_or_id)
        if not manifest_path.is_file():
            catalog = pathlib.Path(os.environ.get("PDS4_CATALOG", "/etc/pds4/models.d"))
            candidate = catalog / f"{args.manifest_or_id}.json"
            if not candidate.is_file():
                candidate = pathlib.Path(__file__).resolve().parents[1] / "models.d" / f"{args.manifest_or_id}.json"
            manifest_path = candidate
        manifest = validate_manifest(read_json(manifest_path))
        if len(manifest["artifacts"]) != 1:
            raise PDS4Error("fetch v1 accepts exactly one reviewed artifact")
        artifact = manifest["artifacts"][0]
        url = args.url or ("https://huggingface.co/" + manifest["source"]["repository"] + "/resolve/" +
                           manifest["source"]["revision"] + "/" + urllib.parse.quote(artifact["file"]))
        if urllib.parse.urlsplit(url).scheme != "https":
            raise PDS4Error("model fetch requires HTTPS; use offline import for local media")
        if "/resolve/main/" in url or "/latest/" in url:
            raise PDS4Error("floating download URL refused")
        default_output = pathlib.Path(os.environ.get("XDG_CACHE_HOME", pathlib.Path.home() / ".cache")) / "pds4/fetch" / manifest["id"]
        destination = pathlib.Path(args.output).resolve() if args.output else default_output.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        parsed_path = urllib.parse.unquote(urllib.parse.urlsplit(url).path)
        if manifest["source"]["revision"] not in parsed_path or not parsed_path.endswith("/" + artifact["file"]):
            raise PDS4Error("download URL does not match the reviewed revision and artifact")
        request = urllib.request.Request(url, headers={"User-Agent": "pds4/0.1"})
        temporary = destination / (artifact["file"] + ".part")
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("xb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        digest, size = sha256_file(temporary)
        if digest != artifact["sha256"] or size != artifact["size"]:
            rejected_dir = destination / "quarantine"
            rejected_dir.mkdir(mode=0o700, exist_ok=True)
            rejected = rejected_dir / (temporary.name + ".bad")
            os.replace(temporary, rejected)
            raise PDS4Error(f"download verification failed; quarantined at {rejected}")
        if artifact["role"] == "weights" and temporary.suffixes[-2:] == [".gguf", ".part"]:
            inspect_gguf(temporary)
        final = destination / artifact["file"]
        temporary.replace(final)
        print(f"verified unprivileged download: {final}; privileged model import is still required")
        return 0
    raise PDS4Error("missing model command")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="pds4")
    commands = root.add_subparsers(dest="command", required=True)
    model = commands.add_parser("model")
    model_commands = model.add_subparsers(dest="model_command", required=True)
    verify = model_commands.add_parser("verify")
    verify.add_argument("model_id")
    inspect = model_commands.add_parser("inspect")
    inspect.add_argument("manifest")
    model_commands.add_parser("list")
    importer = model_commands.add_parser("import")
    importer.add_argument("manifest")
    importer.add_argument("artifacts")
    fetch = model_commands.add_parser("fetch")
    fetch.add_argument("manifest_or_id")
    fetch.add_argument("--url")
    fetch.add_argument("--output")
    gpu = commands.add_parser("gpu")
    gpu_commands = gpu.add_subparsers(dest="gpu_command", required=True)
    probe = gpu_commands.add_parser("probe")
    probe.add_argument("--flash")
    probe.add_argument("--fast")
    lane = commands.add_parser("lane")
    lane_commands = lane.add_subparsers(dest="lane_command", required=True)
    lane_commands.add_parser("status")
    start = lane_commands.add_parser("start")
    start.add_argument("lane", choices=["flash"])
    stop = lane_commands.add_parser("stop")
    stop.add_argument("lane", choices=["flash"])
    use = lane_commands.add_parser("use")
    use.add_argument("lane", choices=["fast"])
    use.add_argument("model_id")
    commands.add_parser("doctor")
    bundle = commands.add_parser("bundle")
    bundle_commands = bundle.add_subparsers(dest="bundle_command", required=True)
    create = bundle_commands.add_parser("create")
    create.add_argument("--model", action="append", default=[])
    create.add_argument("--include-sources", action="store_true")
    create.add_argument("--include-runtime", action="store_true")
    create.add_argument("--personal-use", action="store_true")
    create.add_argument("--signing-key", required=True)
    create.add_argument("--signer", required=True)
    create.add_argument("--output", required=True)
    verify = bundle_commands.add_parser("verify")
    verify.add_argument("path")
    verify.add_argument("--allowed-signers", required=True)
    importer = bundle_commands.add_parser("import")
    importer.add_argument("path")
    importer.add_argument("--allowed-signers", required=True)
    recover = commands.add_parser("recover")
    recover.add_argument("--bundle", required=True)
    recover.add_argument("--allowed-signers", required=True)
    cache = commands.add_parser("cache")
    cache_commands = cache.add_subparsers(dest="cache_command", required=True)
    cache_commands.add_parser("list")
    for name in ("inspect", "checkpoint", "restore"):
        operation = cache_commands.add_parser(name)
        operation.add_argument("session")
    verify_cache = cache_commands.add_parser("verify")
    verify_cache.add_argument("session", nargs="?")
    prune_cache = cache_commands.add_parser("prune")
    prune_cache.add_argument("--max-size", required=True)
    tui = commands.add_parser("tui")
    tui.add_argument("arguments", nargs=argparse.REMAINDER)
    commands.add_parser("serve")
    benchmark = commands.add_parser("benchmark")
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command", required=True)
    benchmark_commands.add_parser("plan")
    run_benchmark = benchmark_commands.add_parser("run")
    run_benchmark.add_argument("--model", required=True)
    run_benchmark.add_argument("--url", default="http://127.0.0.1:8080/v1/chat/completions")
    run_benchmark.add_argument("--key-file", required=True)
    run_benchmark.add_argument("--prompt-file", required=True)
    run_benchmark.add_argument("--context", type=int, required=True)
    run_benchmark.add_argument("--max-tokens", type=int, default=256)
    run_benchmark.add_argument("--iterations", type=int, default=3)
    run_benchmark.add_argument("--output", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if args.command == "model":
            return command_model(args, Paths.environment())
        if args.command == "gpu":
            gpus = discover_gpus()
            for gpu in gpus:
                print(f"{gpu.uuid}\tindex={gpu.index}\tpci={gpu.pci_bus}\tmemory_mib={gpu.memory_mib}\tcompute={gpu.compute}")
            if bool(args.flash) != bool(args.fast):
                raise PDS4Error("--flash and --fast must be supplied together")
            if args.flash:
                assign_gpus(args.flash, args.fast, Paths.environment(), gpus)
                print("GPU assignment written; run systemctl daemon-reload before starting lanes")
            return 0
        if args.command == "lane":
            if args.lane_command == "status":
                print(json.dumps({name: read_lane_state(Paths.environment(), name)
                                  for name in ("flash", "fast")}, indent=2, sort_keys=True))
                return 0
            if args.lane_command in {"start", "stop"}:
                print(json.dumps(flash_action(args.lane_command, Paths.environment()), sort_keys=True))
                return 0
            print(json.dumps(switch_fast(args.model_id, Paths.environment()), sort_keys=True))
            return 0
        if args.command == "doctor":
            result = doctor_inspect(Paths.environment())
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0 if result["ok"] else 1
        if args.command == "bundle":
            if args.bundle_command == "create":
                result = bundle_create(pathlib.Path(args.output), args.model, Paths.environment(),
                                       include_sources=args.include_sources,
                                       include_runtime=args.include_runtime,
                                       personal_use=args.personal_use,
                                       signing_key=pathlib.Path(args.signing_key) if args.signing_key else None,
                                       signer=args.signer)
                print(result["id"])
                return 0
            allowed = pathlib.Path(args.allowed_signers)
            if args.bundle_command == "verify":
                print(json.dumps(bundle_verify(pathlib.Path(args.path), allowed_signers=allowed),
                                 indent=2, sort_keys=True))
                return 0
            imported = import_bundle(pathlib.Path(args.path), Paths.environment(), allowed_signers=allowed)
            print("\n".join(imported))
            return 0
        if args.command == "recover":
            print(bundle_recover(pathlib.Path(args.bundle), Paths.environment(),
                                 allowed_signers=pathlib.Path(args.allowed_signers)))
            return 0
        if args.command == "cache":
            paths = Paths.environment()
            if args.cache_command == "list":
                print(json.dumps(list_checkpoints(paths), indent=2, sort_keys=True))
            elif args.cache_command == "inspect":
                print(json.dumps(cache_inspect(paths, args.session), indent=2, sort_keys=True))
            elif args.cache_command == "checkpoint":
                print(json.dumps(cache_checkpoint(paths, args.session), sort_keys=True))
            elif args.cache_command == "restore":
                print(cache_restore(paths, args.session))
            elif args.cache_command == "verify":
                sessions = [args.session] if args.session else [item["session_id"] for item in list_checkpoints(paths)]
                for session in sessions:
                    verify_checkpoint(paths, session)
                    print(session)
            else:
                print("\n".join(cache_prune(paths, parse_size(args.max_size))))
            return 0
        if args.command == "tui":
            default_tui = pathlib.Path(sys.argv[0]).resolve().with_name("pds4-tui")
            if not default_tui.is_file():
                default_tui = pathlib.Path(__file__).resolve().parents[1] / "scripts/pds4-tui.py"
            tui_path = pathlib.Path(os.environ.get("PDS4_TUI_PATH", default_tui))
            return subprocess.run([sys.executable, str(tui_path), *args.arguments], check=False).returncode
        if args.command == "serve":
            from .gateway import main as gateway_main
            return gateway_main([])
        if args.command == "benchmark":
            if args.benchmark_command == "plan":
                print(json.dumps(benchmark_plan(), indent=2, sort_keys=True))
                return 0
            if args.iterations < 1 or args.iterations > 100 or args.context < 1 or args.max_tokens < 1:
                raise PDS4Error("invalid benchmark iteration, context or token count")
            prompt = pathlib.Path(args.prompt_file).read_bytes()
            if len(prompt) > 1024 * 1024:
                raise PDS4Error("benchmark prompt is too large")
            hardware_before = hardware_snapshot()
            measurements = [run_request(args.url, pathlib.Path(args.key_file), args.model, prompt,
                                        args.context, args.max_tokens) for _ in range(args.iterations)]
            hardware_after = hardware_snapshot()
            result = benchmark_record(Paths.environment(), args.model, prompt, measurements,
                                      [{"phase": "before", "gpus": hardware_before},
                                       {"phase": "after", "gpus": hardware_after}], pathlib.Path(args.output))
            print(result["id"])
            return 0
        raise PDS4Error("unsupported command")
    except PDS4Error as exc:
        print(f"pds4: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
