from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ChapterMapEntry:
    chapter_id: int
    title: str | None
    href: str
    spine_index: int
    block_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

