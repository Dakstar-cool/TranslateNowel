from __future__ import annotations

from dataclasses import dataclass
import warnings

from bs4 import BeautifulSoup
from bs4 import XMLParsedAsHTMLWarning


TEXT_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote")


@dataclass(frozen=True)
class HtmlBlock:
    block_index: int
    paragraph_index: int
    tag_name: str
    text: str


def extract_blocks(html: str) -> list[HtmlBlock]:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")
    blocks: list[HtmlBlock] = []
    paragraph_index = 0
    for index, tag in enumerate(soup.find_all(TEXT_TAGS)):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        blocks.append(HtmlBlock(index, paragraph_index, tag.name or "p", text))
        paragraph_index += 1
    return blocks


def replace_blocks(html: str, replacements: dict[int, str]) -> str:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        soup = BeautifulSoup(html, "lxml")
    for index, tag in enumerate(soup.find_all(TEXT_TAGS)):
        if index not in replacements:
            continue
        tag.clear()
        tag.append(replacements[index])
    return str(soup)
