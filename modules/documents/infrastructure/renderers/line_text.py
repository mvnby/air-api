"""Restricted line-text formatting: emphasis only, with all other text literal."""

from dataclasses import dataclass
import re


_EMPHASIS = re.compile(r"(?<!\*)(\*\*\*|\*\*|\*)(?!\*)(?=\S)(.+?)(?<=\S)\1(?!\*)", re.DOTALL)


@dataclass(frozen=True)
class LineTextRun:
    text: str
    bold: bool = False
    italic: bool = False


def parse_line_text(value: str, *, bold: bool = False, italic: bool = False) -> list[LineTextRun]:
    """Keep HTML, links, unmatched markers and line breaks as ordinary text."""
    runs: list[LineTextRun] = []
    cursor = 0
    for match in _EMPHASIS.finditer(value):
        if match.start() > cursor:
            runs.append(LineTextRun(value[cursor:match.start()], bold, italic))
        marker = match.group(1)
        runs.extend(parse_line_text(
            match.group(2),
            bold=bold or len(marker) >= 2,
            italic=italic or len(marker) in (1, 3),
        ))
        cursor = match.end()
    if cursor < len(value):
        runs.append(LineTextRun(value[cursor:], bold, italic))
    return runs


def google_line_text_requests(value: str, index: int) -> list[dict]:
    """Google Docs offsets count UTF-16 units, including astral characters."""
    runs = parse_line_text(value.replace("\r\n", "\n").replace("\r", "\n"))
    requests = [{"insertText": {"location": {"index": index}, "text": "".join(run.text for run in runs)}}]
    if any(run.bold or run.italic for run in runs):
        end = index + sum(len(run.text.encode("utf-16-le")) // 2 for run in runs)
        requests.append({"updateTextStyle": {
            "range": {"startIndex": index, "endIndex": end},
            "textStyle": {"bold": False, "italic": False},
            "fields": "bold,italic",
        }})
    for run in runs:
        end = index + len(run.text.encode("utf-16-le")) // 2
        style = {}
        if run.bold:
            style["bold"] = True
        if run.italic:
            style["italic"] = True
        if style and end > index:
            requests.append({"updateTextStyle": {
                "range": {"startIndex": index, "endIndex": end},
                "textStyle": style,
                "fields": ",".join(style),
            }})
        index = end
    return requests
