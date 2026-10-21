"""Expose Word content-control contents to the ordinary DOCX renderer."""

from __future__ import annotations

from docx.oxml.ns import qn


def iter_story_roots(document):
    # Only visit existing stories: accessing section.header would create a new
    # part when that section has no header of its own.
    yield document._element
    yield from (
        part.element
        for part in document.part.related_parts.values()
        if part.content_type in {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml",
        }
    )


def unwrap_content_controls(document) -> bool:
    """Remove only SDT wrappers in a working copy, preserving their contents.

    python-docx omits block/row/cell controls from its paragraph/table APIs.
    Promoting their existing XML children also lets the normal condition and
    table processors handle them, without rebuilding text, styles or drawings.
    """
    changed = False
    for root in iter_story_roots(document):
        for control in reversed(list(root.iter(qn("w:sdt")))):
            content = control.find(qn("w:sdtContent"))
            parent = control.getparent()
            if content is None or parent is None:
                continue
            index = parent.index(control)
            for child in list(content):
                parent.insert(index, child)
                index += 1
            parent.remove(control)
            changed = True
    return changed
