from __future__ import annotations

import httpx

from epub_llm_translate.config import ModelEndpointConfig

from .base import BackendUnavailableError, ChatMessage


class OllamaBackend:
    def __init__(self, config: ModelEndpointConfig):
        self.config = config
        self.endpoint = config.endpoint or "http://127.0.0.1:11434/api/chat"

    def generate(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_ctx": self.config.num_ctx,
            },
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(None, connect=10.0)) as client:
                response = client.post(self.endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BackendUnavailableError(_http_error_message(self.endpoint, exc)) from exc
        except httpx.RequestError as exc:
            raise BackendUnavailableError(f"Cannot reach LLM backend at {self.endpoint}: {exc}") from exc
        data = response.json()
        return (data.get("message") or {}).get("content", "").strip()


def _http_error_message(endpoint: str, exc: httpx.HTTPStatusError) -> str:
    body = " ".join(exc.response.text.split())[:300]
    suffix = f": {body}" if body else ""
    return f"LLM backend rejected request with HTTP {exc.response.status_code} at {endpoint}{suffix}"
