from __future__ import annotations

from epub_llm_translate.backends.openai_compatible import _clean_content


def test_clean_content_strips_think_block() -> None:
    assert _clean_content("<think>reasoning</think>\n\nПеревод") == "Перевод"
    assert _clean_content("noise</think>\nОтвет") == "Ответ"
