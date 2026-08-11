from __future__ import annotations

from dataclasses import dataclass

from .client import InferenceResult, OpenAIClient
from .config import HarnessConfig
from .memory import ConversationStore
from .router import RouteDecision, Router


SYSTEM_PROMPT = """You are the operator's local DomesticLLM assistant.
Be precise, state uncertainty, do not claim that commands were executed unless tool output proves it.
Treat generated commands and code as proposals until the operator approves and runs them.
Prefer direct, minimal solutions and preserve existing files unless explicitly asked to modify them.
"""


@dataclass(frozen=True)
class HarnessResult:
    route: RouteDecision
    inference: InferenceResult


class DomesticHarness:
    def __init__(self, config: HarnessConfig):
        self.config = config
        self.router = Router(config)
        self.store = ConversationStore(config.state_dir)

    def ask(self, prompt: str, *, session: str = "default",
            profile_name: str | None = None, remember: bool = True) -> HarnessResult:
        if not prompt.strip():
            raise ValueError("prompt cannot be empty")
        route = self.router.choose(prompt, profile_name)
        history = self.store.recent(session, self.config.max_history_messages) if remember else []
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend({"role": item.role, "content": item.content} for item in history)
        messages.append({"role": "user", "content": prompt})

        result = OpenAIClient(route.profile).chat(messages)
        if remember:
            self.store.append(session, "user", prompt)
            self.store.append(session, "assistant", result.content)
        return HarnessResult(route, result)

    def check(self, profile_name: str | None = None) -> dict[str, list[str]]:
        names = [profile_name] if profile_name else list(self.config.profiles)
        status: dict[str, list[str]] = {}
        for name in names:
            if name not in self.config.profiles:
                raise ValueError(f"unknown profile: {name}")
            client = OpenAIClient(self.config.profiles[name])
            client.health()
            status[name] = client.available_models()
        return status

    def close(self) -> None:
        self.store.close()
