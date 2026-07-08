from __future__ import annotations

import json
import re

from epub_llm_translate.config import ModelEndpointConfig

from .base import ChatMessage


class FakeBackend:
    def __init__(self, config: ModelEndpointConfig):
        self.config = config

    def generate(self, messages: list[ChatMessage]) -> str:
        last = messages[-1].content if messages else ""
        if "Input batch:" in last and "revised_text" in last:
            match = re.search(r"Input batch:\n(.*)\s*$", last, flags=re.DOTALL)
            if match:
                try:
                    items = json.loads(match.group(1))
                    return json.dumps(
                        [
                            {
                                "block_id": item["block_id"],
                                "revised_text": f"FAKE_REVISED {item.get('paragraph_index', 0)}",
                            }
                            for item in items
                        ],
                        ensure_ascii=False,
                    )
                except (KeyError, TypeError, json.JSONDecodeError):
                    pass
        marker = "TARGET:"
        if marker in last:
            return last.split(marker, 1)[1].strip().splitlines()[0]
        return "FAKE_LOCAL_MODEL_OUTPUT"
