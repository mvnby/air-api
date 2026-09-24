"""Normalize legacy Word form fields while keeping their visible values."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from lxml import etree


_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_FLD_CHAR = f"{{{_WORD_NS}}}fldChar"
_FIELD_INSTRUCTION = f"{{{_WORD_NS}}}instrText"
_FIELD_TYPE = f"{{{_WORD_NS}}}fldCharType"
_FORM_DATA = f"{{{_WORD_NS}}}ffData"


def flatten_legacy_form_fields(content: bytes) -> bytes:
    """Turn legacy FORMTEXT/FORMCHECKBOX fields into ordinary DOCX content.

    Word stores a field's visible result separately from its form-control
    markers. Removing only the markers preserves the displayed text, run
    formatting, and the rest of the DOCX package.
    """

    source = BytesIO(content)
    output = BytesIO()
    changed = False
    parser = etree.XMLParser(resolve_entities=False, no_network=True)

    with ZipFile(source, "r") as archive:
        entries = [(entry, archive.read(entry.filename)) for entry in archive.infolist()]
    normalized_entries: list[tuple[ZipInfo, bytes]] = []
    for entry, data in entries:
        if not entry.filename.startswith("word/") or not entry.filename.endswith(".xml"):
            normalized_entries.append((entry, data))
            continue
        try:
            root = etree.fromstring(data, parser)
        except etree.XMLSyntaxError:
            normalized_entries.append((entry, data))
            continue

        field_stack: list[bool] = []
        remove: list[etree._Element] = []
        for node in root.iter():
            if node.tag == _FLD_CHAR:
                field_type = node.get(_FIELD_TYPE)
                inside_form_field = any(field_stack)
                if field_type == "begin":
                    is_form_field = node.find(_FORM_DATA) is not None
                    if inside_form_field or is_form_field:
                        remove.append(node)
                    field_stack.append(is_form_field)
                else:
                    if inside_form_field:
                        remove.append(node)
                    if field_type == "end" and field_stack:
                        field_stack.pop()
            elif node.tag == _FIELD_INSTRUCTION and any(field_stack):
                remove.append(node)

        if remove:
            for node in remove:
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)
            data = etree.tostring(
                root,
                encoding="UTF-8",
                xml_declaration=True,
                standalone=True,
            )
            changed = True
        normalized_entries.append((entry, data))

    if not changed:
        return content

    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for entry, data in normalized_entries:
            archive.writestr(entry, data)
    return output.getvalue()
