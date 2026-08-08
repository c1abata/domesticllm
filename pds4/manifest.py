from __future__ import annotations

import re
from typing import Any

from .common import PDS4Error


ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{1,126}[a-z0-9]$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40,64}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
STATES = {"quarantine", "verified", "canary", "promoted"}
LANES = {"flash", "fast"}
ARTIFACT_ROLES = {"weights", "tokenizer", "template", "steering", "imatrix", "license"}


def _required(mapping: dict[str, Any], name: str, expected: type) -> Any:
    value = mapping.get(name)
    if not isinstance(value, expected) or expected is str and not value:
        raise PDS4Error(f"manifest field {name!r} has the wrong type")
    return value


def validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PDS4Error("manifest must be an object")
    if value.get("schema") != 1:
        raise PDS4Error("unsupported model manifest schema")
    model_id = _required(value, "id", str)
    if not ID_PATTERN.fullmatch(model_id):
        raise PDS4Error("invalid model id")
    _required(value, "family", str)
    _required(value, "purpose", str)
    source = _required(value, "source", dict)
    if not REPOSITORY.fullmatch(_required(source, "repository", str)):
        raise PDS4Error("source repository must be an owner/name identifier")
    revision = _required(source, "revision", str)
    if not REVISION.fullmatch(revision):
        raise PDS4Error("source revision must be an immutable 40-64 digit hexadecimal revision")
    artifacts = _required(value, "artifacts", list)
    if not artifacts:
        raise PDS4Error("manifest has no artifacts")
    seen_files: set[str] = set()
    has_weights = False
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            raise PDS4Error(f"artifact {index} is not an object")
        filename = _required(artifact, "file", str)
        if filename != filename.rsplit("/", 1)[-1] or filename in {".", ".."} or filename.startswith("."):
            raise PDS4Error(f"artifact {index} has an unsafe filename")
        if filename in seen_files:
            raise PDS4Error(f"duplicate artifact filename: {filename}")
        seen_files.add(filename)
        role = _required(artifact, "role", str)
        if role not in ARTIFACT_ROLES:
            raise PDS4Error(f"unsupported artifact role: {role}")
        has_weights |= role == "weights"
        digest = _required(artifact, "sha256", str)
        if not HEX64.fullmatch(digest):
            raise PDS4Error(f"artifact {filename} has an invalid SHA-256")
        size = artifact.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            raise PDS4Error(f"artifact {filename} has an invalid size")
    if not has_weights:
        raise PDS4Error("manifest has no weights artifact")
    runtime = _required(value, "runtime", dict)
    if _required(runtime, "engine", str) not in {"ds4", "llama.cpp"}:
        raise PDS4Error("unsupported runtime engine")
    if not REVISION.fullmatch(_required(runtime, "commit", str)):
        raise PDS4Error("runtime commit is not immutable")
    if value.get("lane") not in LANES:
        raise PDS4Error("lane must be flash or fast")
    context = value.get("context_tested")
    if not isinstance(context, int) or isinstance(context, bool) or context < 1:
        raise PDS4Error("context_tested must be a positive integer")
    if not isinstance(value.get("tools_allowed"), bool):
        raise PDS4Error("tools_allowed must be boolean")
    license_data = _required(value, "license", dict)
    _required(license_data, "spdx", str)
    if license_data.get("redistribution") not in {"allowed", "personal-only", "metadata-only", "unknown"}:
        raise PDS4Error("invalid license redistribution policy")
    if value.get("status") not in STATES:
        raise PDS4Error("invalid model status")
    if value.get("offline_ready") is not True:
        raise PDS4Error("offline_ready must be true")
    if value.get("id") == "dolphin-cyber-8b-q4" and value.get("tools_allowed"):
        raise PDS4Error("Cyber model must not enable tools")
    return value
