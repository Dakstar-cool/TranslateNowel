from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re


HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def text_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def parse_chapter_range(value: str | None, default: tuple[int, int]) -> list[int]:
    if not value:
        start, end = default
        return list(range(start, end + 1))
    result: list[int] = []
    for part in value.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            left, right = token.split("-", 1)
            start = int(left)
            end = int(right)
            if end < start:
                raise ValueError(f"Invalid chapter range: {token}")
            result.extend(range(start, end + 1))
        else:
            result.append(int(token))
    return sorted(set(result))


def contains_hangul(text: str | None) -> bool:
    return bool(text and HANGUL_RE.search(text))


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."

