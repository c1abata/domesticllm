from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.parse
import urllib.request

from .common import Paths, PDS4Error, read_json, sha256_file
from .gpu import assign as assign_gpus, discover as discover_gpus
from .manifest import validate_manifest
from .store import import_model, inspect_gguf, quarantine, verify_installed


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
        if args.url is None:
            raise PDS4Error("fetch requires an explicit immutable --url")
        if "/resolve/main/" in args.url or "/latest/" in args.url:
            raise PDS4Error("floating download URL refused")
        manifest_path = pathlib.Path(args.manifest)
        manifest = validate_manifest(read_json(manifest_path))
        if len(manifest["artifacts"]) != 1:
            raise PDS4Error("fetch v1 accepts exactly one reviewed artifact")
        destination = pathlib.Path(args.output).resolve()
        destination.mkdir(parents=True, exist_ok=True)
        artifact = manifest["artifacts"][0]
        parsed_path = urllib.parse.unquote(urllib.parse.urlsplit(args.url).path)
        if manifest["source"]["revision"] not in parsed_path or not parsed_path.endswith("/" + artifact["file"]):
            raise PDS4Error("download URL does not match the reviewed revision and artifact")
        request = urllib.request.Request(args.url, headers={"User-Agent": "pds4/0.1"})
        temporary = destination / (artifact["file"] + ".part")
        with urllib.request.urlopen(request, timeout=60) as response, temporary.open("xb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        digest, size = sha256_file(temporary)
        if digest != artifact["sha256"] or size != artifact["size"]:
            rejected = quarantine(temporary, "downloaded artifact failed size or SHA-256 verification", Paths(destination))
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
    fetch.add_argument("manifest")
    fetch.add_argument("--url", required=True)
    fetch.add_argument("--output", required=True)
    gpu = commands.add_parser("gpu")
    gpu_commands = gpu.add_subparsers(dest="gpu_command", required=True)
    probe = gpu_commands.add_parser("probe")
    probe.add_argument("--flash")
    probe.add_argument("--fast")
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
        raise PDS4Error("unsupported command")
    except PDS4Error as exc:
        print(f"pds4: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
