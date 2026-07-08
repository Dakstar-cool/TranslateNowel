from __future__ import annotations

from pathlib import Path


def load_style_guide(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")

