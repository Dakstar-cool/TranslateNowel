from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from epub_llm_translate.config import ModelEndpointConfig


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


class BackendUnavailableError(RuntimeError):
    """Raised when the local LLM backend cannot be reached or is unavailable."""


class ChatBackend(Protocol):
    def generate(self, messages: list[ChatMessage]) -> str:
        ...


def create_backend(config: ModelEndpointConfig) -> ChatBackend:
    if config.backend == "ollama":
        from .ollama import OllamaBackend

        return OllamaBackend(config)
    if config.backend == "openai_compatible":
        from .openai_compatible import OpenAICompatibleBackend

        return OpenAICompatibleBackend(config)
    if config.backend == "fake":
        from .fake import FakeBackend

        return FakeBackend(config)
    raise ValueError(f"Unsupported backend: {config.backend}")
