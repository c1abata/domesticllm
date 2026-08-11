from __future__ import annotations

from dataclasses import dataclass
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import ModelProfile


class InferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class InferenceResult:
    profile: str
    model: str
    content: str
    prompt_tokens: int | None
    completion_tokens: int | None
    elapsed_seconds: float


class OpenAIClient:
    def __init__(self, profile: ModelProfile):
        self.profile = profile

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.profile.base_url}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.profile.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.profile.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:2000]
            raise InferenceError(f"server returned HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise InferenceError(f"cannot reach {self.profile.base_url}: {exc}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InferenceError("server returned invalid JSON") from exc

    def health(self) -> None:
        self._request("GET", "/health")

    def available_models(self) -> list[str]:
        payload = self._request("GET", "/v1/models")
        return [item["id"] for item in payload.get("data", []) if isinstance(item, dict) and item.get("id")]

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int | None = None,
             temperature: float | None = None) -> InferenceResult:
        payload = {
            "model": self.profile.model,
            "messages": messages,
            "max_tokens": max_tokens or self.profile.max_tokens,
            "temperature": self.profile.temperature if temperature is None else temperature,
            "stream": False,
        }
        started = time.monotonic()
        response = self._request("POST", "/v1/chat/completions", payload)
        elapsed = time.monotonic() - started
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceError(f"unexpected completion response: {response}") from exc
        usage = response.get("usage") or {}
        return InferenceResult(
            profile=self.profile.name,
            model=response.get("model", self.profile.model),
            content=str(content),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            elapsed_seconds=elapsed,
        )
