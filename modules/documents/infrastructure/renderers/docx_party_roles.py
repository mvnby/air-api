"""Replace literal party labels before inserting personal and commercial data."""
from __future__ import annotations

from io import BytesIO
import re

from docx import Document
from docx.oxml.ns import qn

from modules.documents.domain.roles import ROLE_FORMS, role_word_replacements
from .docx_conditions import DocxConditionProcessor


_PLACEHOLDER = re.compile(r"{{.*?}}", re.DOTALL)


def detect_template_role_type(source: bytes) -> str | None:
    """Infer only an unambiguous pair from template literals, never field values."""
    document = Document(BytesIO(source))
    text = "\n".join(
        _PLACEHOLDER.sub("", paragraph.text).lower()
        for paragraphs in DocxConditionProcessor()._all_paragraph_collections(document)
        for paragraph in paragraphs
    )
    words = set(re.findall(r"[а-яё]+", text))
    matches = [
        name for name, (seller, customer) in ROLE_FORMS.items()
        if words.intersection(seller.values()) and words.intersection(customer.values())
    ]
    return matches[0] if len(matches) == 1 else None


def replace_party_role_words(paragraph, role_type: str) -> None:
    replacements = role_word_replacements(role_type)
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, replacements)) + r")(?!\w)")
    nodes = list(paragraph._p.iter(qn("w:t")))
    source = "".join(node.text or "" for node in nodes)
    protected = [match.span() for match in _PLACEHOLDER.finditer(source)]
    matches = [
        match for match in pattern.finditer(source)
        if not any(start <= match.start() < end for start, end in protected)
    ]
    positions = []
    cursor = 0
    for node in nodes:
        end = cursor + len(node.text or "")
        positions.append((cursor, end))
        cursor = end
    for match in reversed(matches):
        replacement = replacements[match.group()]
        if replacement == match.group():
            continue
        first = next(i for i, (start, end) in enumerate(positions) if start <= match.start() < end)
        last = next(i for i, (start, end) in enumerate(positions) if start < match.end() <= end)
        prefix = (nodes[first].text or "")[:match.start() - positions[first][0]]
        suffix = (nodes[last].text or "")[match.end() - positions[last][0]:]
        if first == last:
            nodes[first].text = prefix + replacement + suffix
        else:
            nodes[first].text = prefix + replacement
            for i in range(first + 1, last):
                nodes[i].text = ""
            nodes[last].text = suffix
        for node in nodes[first:last + 1]:
            if (node.text or "").startswith(" ") or (node.text or "").endswith(" "):
                node.set(qn("xml:space"), "preserve")
