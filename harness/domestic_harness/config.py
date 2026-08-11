from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import tomllib


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelProfile:
    name: str
    base_url: str
    model: str
    api_key_env: str
    capabilities: frozenset[str]
    timeout_seconds: float = 300.0
    max_tokens: int = 1536
    temperature: float = 0.15

    @property
    def api_key(self) -> str:
        value = os.environ.get(self.api_key_env, "").strip()
        if not value:
            raise ConfigError(f"missing environment variable: {self.api_key_env}")
        return value


@dataclass(frozen=True)
class HarnessConfig:
    default_profile: str
    state_dir: Path
    max_history_messages: int
    profiles: dict[str, ModelProfile]


def _required_string(table: dict, key: str, where: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}.{key} must be a non-empty string")
    return value.strip()


def load_config(path: Path) -> HarnessConfig:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read configuration {path}: {exc}") from exc

    harness = raw.get("harness")
    models = raw.get("models")
    if not isinstance(harness, dict) or not isinstance(models, dict) or not models:
        raise ConfigError("configuration requires [harness] and at least one [models.NAME]")

    default_profile = _required_string(harness, "default_profile", "harness")
    state_dir = Path(os.path.expanduser(_required_string(harness, "state_dir", "harness")))
    max_history = harness.get("max_history_messages", 24)
    if not isinstance(max_history, int) or not 1 <= max_history <= 200:
        raise ConfigError("harness.max_history_messages must be between 1 and 200")

    profiles: dict[str, ModelProfile] = {}
    for name, table in models.items():
        if not isinstance(table, dict):
            raise ConfigError(f"models.{name} must be a table")
        capabilities = table.get("capabilities", [])
        if not isinstance(capabilities, list) or not all(isinstance(x, str) for x in capabilities):
            raise ConfigError(f"models.{name}.capabilities must be a string array")
        base_url = _required_string(table, "base_url", f"models.{name}").rstrip("/")
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError(f"models.{name}.base_url must be HTTP(S)")
        profiles[name] = ModelProfile(
            name=name,
            base_url=base_url,
            model=_required_string(table, "model", f"models.{name}"),
            api_key_env=_required_string(table, "api_key_env", f"models.{name}"),
            capabilities=frozenset(capabilities),
            timeout_seconds=float(table.get("timeout_seconds", 300)),
            max_tokens=int(table.get("max_tokens", 1536)),
            temperature=float(table.get("temperature", 0.15)),
        )

    if default_profile not in profiles:
        raise ConfigError(f"unknown default profile: {default_profile}")
    return HarnessConfig(default_profile, state_dir, max_history, profiles)
