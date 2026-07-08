from __future__ import annotations

import httpx

from epub_llm_translate.config import ModelEndpointConfig

from .base import BackendUnavailableError, ChatMessage


class OpenAICompatibleBackend:
    def __init__(self, config: ModelEndpointConfig):
        if not config.endpoint:
            raise ValueError("openai_compatible backend requires endpoint")
        endpoint = config.endpoint.rstrip("/")
        if not (
            endpoint.startswith("http://127.0.0.1:")
            or endpoint.startswith("http://localhost:")
            or endpoint.startswith("http://[::1]:")
        ):
            raise ValueError("Only local OpenAI-compatible endpoints are allowed by default")
        self.config = config
        self.endpoint = endpoint

    def generate(self, messages: list[ChatMessage]) -> str:
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.max_output_tokens,
        }
        if self.config.disable_thinking:
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        payload.update(self.config.extra_body)
        try:
            with httpx.Client(timeout=httpx.Timeout(None, connect=10.0)) as client:
                response = client.post(self.endpoint, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BackendUnavailableError(_http_error_message(self.endpoint, exc)) from exc
        except httpx.RequestError as exc:
            raise BackendUnavailableError(f"Cannot reach LLM backend at {self.endpoint}: {exc}") from exc
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return _clean_content(message.get("content") or "").strip()


def _clean_content(content: str) -> str:
    text = content.strip()
    if "</think>" in text:
        text = text.split("</think>", 1)[1].strip()
    while "<think>" in text and "</think>" in text:
        before, rest = text.split("<think>", 1)
        _thinking, after = rest.split("</think>", 1)
        text = f"{before}{after}".strip()
    return text


def _http_error_message(endpoint: str, exc: httpx.HTTPStatusError) -> str:
    body = " ".join(exc.response.text.split())[:300]
    suffix = f": {body}" if body else ""
    return f"LLM backend rejected request with HTTP {exc.response.status_code} at {endpoint}{suffix}"
