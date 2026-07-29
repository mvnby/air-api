from __future__ import annotations

import html
import re
from html.parser import HTMLParser


_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
_IGNORED_TAGS = {"script", "style", "noscript"}
_LEADING_CSS_BLOCK = re.compile(
    r"^\s*(?:[.#][\w-]+(?:\s+[*\w.#:[\]=\"'-]+)*\s*\{[^{}]*\}\s*)+",
    flags=re.DOTALL,
)


class _PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.lower()
        if normalized in _IGNORED_TAGS:
            self._ignored_depth += 1
            return
        if not self._ignored_depth and normalized in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in _IGNORED_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if not self._ignored_depth and normalized in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def sanitize_yandex_description(value: str | None, *, fallback: str, limit: int) -> str:
    raw = html.unescape(value or "")
    raw = _LEADING_CSS_BLOCK.sub("", raw)
    parser = _PlainTextParser()
    parser.feed(raw)
    parser.close()
    text = re.sub(r"\s+", " ", "".join(parser.parts)).strip()
    text = _LEADING_CSS_BLOCK.sub("", text).strip()
    text = text or re.sub(r"\s+", " ", fallback).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
