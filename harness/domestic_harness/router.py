from __future__ import annotations

from dataclasses import dataclass
import re

from .config import HarnessConfig, ModelProfile


@dataclass(frozen=True)
class RouteDecision:
    profile: ModelProfile
    task: str
    reason: str


_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("security", re.compile(r"\b(cve|vulnerabil|hardening|firewall|soc|nmap|incident|malware)\b", re.I)),
    ("code", re.compile(r"\b(code|codice|python|rust|c\+\+|javascript|typescript|debug|refactor|test|api|sql|git)\b", re.I)),
    ("reasoning", re.compile(r"\b(analizza|ragiona|dimostra|confronta|architettura|progetta|piano|strategia)\b", re.I)),
    ("general", re.compile(r".*", re.S)),
)


class Router:
    """Small deterministic router. It never invents model capabilities or silently falls back."""

    def __init__(self, config: HarnessConfig):
        self.config = config

    def classify(self, prompt: str) -> str:
        for task, pattern in _RULES:
            if pattern.search(prompt):
                return task
        return "general"

    def choose(self, prompt: str, requested_profile: str | None = None) -> RouteDecision:
        if requested_profile:
            try:
                profile = self.config.profiles[requested_profile]
            except KeyError as exc:
                raise ValueError(f"unknown profile: {requested_profile}") from exc
            return RouteDecision(profile, self.classify(prompt), "explicit operator selection")

        task = self.classify(prompt)
        candidates = [p for p in self.config.profiles.values() if task in p.capabilities]
        if not candidates:
            profile = self.config.profiles[self.config.default_profile]
            return RouteDecision(profile, task, "default profile; no exact capability match")

        # Configuration order is the operator's priority order.
        return RouteDecision(candidates[0], task, f"first configured profile with capability '{task}'")
