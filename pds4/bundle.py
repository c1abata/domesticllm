from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import time
import uuid
from typing import Any

from .common import Paths, PDS4Error, atomic_write, canonical_json, read_json, sha256_file
from .manifest import validate_manifest
from .store import blob_path, import_model, verify_installed


PLATFORM = "ubuntu-24.04-x86_64-sm86"
METADATA = {"BUNDLE.json", "SHA256SUMS", "SHA256SUMS.sig"}


def _regular_files(root: pathlib.Path) -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = pathlib.Path(current)
        for name in directories:
            if (current_path / name).is_symlink():
                raise PDS4Error(f"bundle contains a symlink: {current_path / name}")
        for name in names:
            item = current_path / name
            if item.is_symlink() or not item.is_file() or item.stat().st_nlink != 1:
                raise PDS4Error(f"bundle contains a non-regular file: {item}")
            files.append(item)
    return sorted(files)


def _copy_file(source: pathlib.Path, destination: pathlib.Path, mode: int = 0o440) -> None:
    if source.is_symlink() or not source.is_file():
        raise PDS4Error(f"source is not a regular file: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_file, destination.open("xb") as output_file:
        shutil.copyfileobj(input_file, output_file, 8 * 1024 * 1024)
        output_file.flush()
        os.fsync(output_file.fileno())
    destination.chmod(mode)


def _copy_tree(source: pathlib.Path, destination: pathlib.Path) -> None:
    if source.is_symlink() or not source.is_dir():
        raise PDS4Error(f"source tree is unavailable: {source}")
    for item in _regular_files(source):
        _copy_file(item, destination / item.relative_to(source), item.stat().st_mode & 0o555 or 0o440)


def create(output: pathlib.Path, model_ids: list[str], paths: Paths, *, include_sources: bool = False,
           include_runtime: bool = False, personal_use: bool = False,
           signing_key: pathlib.Path | None = None, signer: str | None = None) -> dict[str, Any]:
    if output.exists():
        raise PDS4Error("bundle output already exists")
    output.mkdir(parents=True, mode=0o750)
    try:
        repository = pathlib.Path(__file__).resolve().parents[1]
        for name in ("build-ds4.sh", "build-llamacpp.sh", "toolchain.lock"):
            source = repository / "build" / name
            _copy_file(source, output / "build" / name, source.stat().st_mode & 0o555 or 0o440)
        _copy_file(repository / "LICENSE", output / "licenses" / "PDS4-LICENSE")
        _copy_file(repository / "vendor.lock.json", output / "sbom" / "vendor.lock.json")
        _copy_file(repository / "docs/PDS4_INVARIANTS.md", output / "docs/PDS4_INVARIANTS.md")
        bootstrap = output / "bootstrap"
        for source in sorted((repository / "pds4").glob("*.py")):
            _copy_file(source, bootstrap / "pds4" / source.name)
        for source in sorted((repository / "scripts").glob("pds4*")):
            if source.is_file() and not source.is_symlink():
                _copy_file(source, bootstrap / "scripts" / source.name, source.stat().st_mode & 0o555 or 0o440)
        for pattern in ("pds4-*.service", "pds4-*.timer"):
            for source in sorted((repository / "systemd").glob(pattern)):
                _copy_file(source, bootstrap / "systemd" / source.name)
        for source in sorted((repository / "systemd/user").glob("pds4-*.service")):
            _copy_file(source, bootstrap / "systemd/user" / source.name)
        for directory, pattern in (("conf", "pds4*"), ("models.d", "*.json"),
                                   ("schemas", "*.json"), ("web", "*"),
                                   ("docs", "PDS4_*.md"), ("build", "*")):
            for source in sorted((repository / directory).glob(pattern)):
                if source.is_file() and not source.is_symlink():
                    _copy_file(source, bootstrap / directory / source.name,
                               source.stat().st_mode & 0o555 or 0o440)
        for name in ("LICENSE", "NOTICE.md", "vendor.lock.json"):
            _copy_file(repository / name, bootstrap / name)
        included_models: list[str] = []
        for model_id in model_ids:
            manifest = verify_installed(model_id, paths)
            model_root = output / "models" / model_id
            _copy_file(paths.models / model_id / "manifest.json", model_root / "manifest.json")
            redistribution = manifest["license"]["redistribution"]
            include_weights = redistribution == "allowed" or personal_use and redistribution == "personal-only"
            for artifact in manifest["artifacts"]:
                if artifact["role"] == "weights" and not include_weights:
                    continue
                _copy_file(blob_path(paths, artifact["sha256"]), model_root / "artifacts" / artifact["file"])
            included_models.append(model_id)
        if include_sources:
            _copy_tree(paths.at("/srv/pds4/sources"), output / "sources")
            for optional in ("patches", "packages", "licenses", "steering"):
                candidate = paths.at(f"/srv/pds4/{optional}")
                if candidate.is_dir():
                    _copy_tree(candidate, output / optional)
        if include_runtime:
            current = paths.at("/opt/pds4/current")
            if not current.is_symlink():
                raise PDS4Error("current PDS4 release is not an immutable symlink")
            _copy_tree(current.resolve(), output / "runtimes" / PLATFORM)
        files: dict[str, dict[str, Any]] = {}
        for item in _regular_files(output):
            relative = item.relative_to(output).as_posix()
            digest, size = sha256_file(item)
            files[relative] = {"sha256": digest, "size": size}
        bundle = {
            "schema": 1, "id": str(uuid.uuid4()), "created_unix": int(time.time()),
            "platform": PLATFORM, "models": included_models, "personal_use": personal_use,
            "signer": signer, "files": files,
        }
        atomic_write(output / "BUNDLE.json", canonical_json(bundle), 0o440)
        checks: list[str] = []
        for item in _regular_files(output):
            if item.name == "SHA256SUMS.sig":
                continue
            digest, _ = sha256_file(item)
            checks.append(f"{digest}  {item.relative_to(output).as_posix()}\n")
        atomic_write(output / "SHA256SUMS", "".join(checks).encode(), 0o440)
        if signing_key:
            if not signer:
                raise PDS4Error("signed bundles require a signer identity")
            try:
                subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(signing_key), "-n", "pds4-bundle",
                                str(output / "SHA256SUMS")], check=True, timeout=30,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except (FileNotFoundError, subprocess.SubprocessError) as exc:
                raise PDS4Error("bundle signing failed") from exc
        return bundle
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def _parse_sums(path: pathlib.Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64 or pathlib.PurePosixPath(parts[1]).is_absolute() or ".." in pathlib.PurePosixPath(parts[1]).parts:
            raise PDS4Error("invalid SHA256SUMS entry")
        if parts[1] in result:
            raise PDS4Error("duplicate SHA256SUMS entry")
        result[parts[1]] = parts[0]
    return result


def verify(root: pathlib.Path, *, allowed_signers: pathlib.Path | None = None,
           require_signature: bool = True) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        raise PDS4Error("bundle root must be a regular directory")
    bundle = read_json(root / "BUNDLE.json")
    if not isinstance(bundle, dict) or bundle.get("schema") != 1 or bundle.get("platform") != PLATFORM:
        raise PDS4Error("unsupported bundle schema or platform")
    declared = bundle.get("files")
    if not isinstance(declared, dict):
        raise PDS4Error("bundle inventory is missing")
    actual_files = {item.relative_to(root).as_posix() for item in _regular_files(root)}
    expected_files = set(declared) | {"BUNDLE.json", "SHA256SUMS"}
    if (root / "SHA256SUMS.sig").exists():
        expected_files.add("SHA256SUMS.sig")
    if actual_files != expected_files:
        raise PDS4Error("bundle has missing or undeclared files")
    sums = _parse_sums(root / "SHA256SUMS")
    if set(sums) != expected_files - {"SHA256SUMS", "SHA256SUMS.sig"}:
        raise PDS4Error("SHA256SUMS inventory differs from bundle")
    for relative, record in declared.items():
        if pathlib.PurePosixPath(relative).is_absolute() or ".." in pathlib.PurePosixPath(relative).parts:
            raise PDS4Error("unsafe bundle inventory path")
        target = root / relative
        digest, size = sha256_file(target)
        if not isinstance(record, dict) or digest != record.get("sha256") or size != record.get("size"):
            raise PDS4Error(f"bundle payload verification failed: {relative}")
        if sums.get(relative) != digest:
            raise PDS4Error(f"SHA256SUMS mismatch: {relative}")
    bundle_digest, _ = sha256_file(root / "BUNDLE.json")
    if sums.get("BUNDLE.json") != bundle_digest:
        raise PDS4Error("BUNDLE.json checksum mismatch")
    signature = root / "SHA256SUMS.sig"
    if require_signature:
        if not signature.is_file() or not allowed_signers or not bundle.get("signer"):
            raise PDS4Error("bundle signature or trust configuration is missing")
        try:
            subprocess.run(["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers),
                            "-I", bundle["signer"], "-n", "pds4-bundle", "-s", str(signature)],
                           input=(root / "SHA256SUMS").read_bytes(), check=True, timeout=30,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise PDS4Error("bundle signature verification failed") from exc
    return bundle


def import_bundle(root: pathlib.Path, paths: Paths, *, allowed_signers: pathlib.Path | None = None,
                  require_signature: bool = True) -> list[str]:
    bundle = verify(root, allowed_signers=allowed_signers, require_signature=require_signature)
    imported: list[str] = []
    for model_id in bundle["models"]:
        model_root = root / "models" / model_id
        manifest = validate_manifest(read_json(model_root / "manifest.json"))
        weights = [item for item in manifest["artifacts"] if item["role"] == "weights"]
        if weights and not (model_root / "artifacts" / weights[0]["file"]).exists():
            continue
        import_model(model_root / "manifest.json", model_root / "artifacts", paths)
        imported.append(model_id)
    return imported


def recover(root: pathlib.Path, paths: Paths, *, allowed_signers: pathlib.Path | None = None,
            require_signature: bool = True) -> str:
    bundle = verify(root, allowed_signers=allowed_signers, require_signature=require_signature)
    import_bundle(root, paths, allowed_signers=allowed_signers, require_signature=require_signature)
    runtime = root / "runtimes" / PLATFORM
    if not runtime.is_dir():
        raise PDS4Error("bundle has no runtime for the recovery platform")
    release_root = paths.at("/opt/pds4/releases")
    release_root.mkdir(parents=True, exist_ok=True)
    release = release_root / bundle["id"]
    if not release.exists():
        temporary = release_root / f".{bundle['id']}.install"
        if temporary.exists():
            shutil.rmtree(temporary)
        _copy_tree(runtime, temporary)
        os.replace(temporary, release)
    current = paths.at("/opt/pds4/current")
    previous = paths.at("/opt/pds4/previous")
    current.parent.mkdir(parents=True, exist_ok=True)
    if current.is_symlink():
        old = current.resolve()
        temporary_previous = previous.with_name(".previous.new")
        temporary_previous.unlink(missing_ok=True)
        temporary_previous.symlink_to(old)
        os.replace(temporary_previous, previous)
    temporary_current = current.with_name(".current.new")
    temporary_current.unlink(missing_ok=True)
    temporary_current.symlink_to(release)
    os.replace(temporary_current, current)
    return bundle["id"]
