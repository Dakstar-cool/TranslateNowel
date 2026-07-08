from __future__ import annotations

from epub_llm_translate.config import ModelEndpointConfig

from .base import ChatMessage


class FakeBackend:
    def __init__(self, config: ModelEndpointConfig):
        self.config = config

    def generate(self, messages: list[ChatMessage]) -> str:
        last = messages[-1].content if messages else ""
        marker = "TARGET:"
        if marker in last:
            return last.split(marker, 1)[1].strip().splitlines()[0]
        return "FAKE_LOCAL_MODEL_OUTPUT"

