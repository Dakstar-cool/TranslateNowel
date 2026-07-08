from __future__ import annotations

from epub_llm_translate.pipeline.draft_translate import _looks_like_meta_output, _postprocess_draft_output


def test_postprocess_fixes_mismatched_smart_quotes() -> None:
    assert _postprocess_draft_output("\u201cТекст\u201c") == "\u201cТекст\u201d"


def test_meta_output_detection() -> None:
    assert _looks_like_meta_output("Analyze the Source:\nKorean: ...")
    assert not _looks_like_meta_output("Ульрих пошел к горному хребту.")
