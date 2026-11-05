"""Remove the retired missing-requisites stamp only from working copies."""

from io import BytesIO

from docx import Document
from docx.parts.hdrftr import HeaderPart

LEGACY_CUSTOMER_MARKER = "ЧЕРНОВИК — не заполнены обязательные поля клиента"


def remove_legacy_customer_marker(content: bytes) -> bytes:
    try:
        document = Document(BytesIO(content))
    except Exception as exc:
        raise ValueError("Черновик DOCX повреждён или не читается") from exc

    # The former renderer inserted a separate paragraph at the beginning of the
    # body and active headers. An editor may subsequently split its runs, or
    # append user text, a signature, or graphics to the very same paragraph.
    stories = [document.element.body]
    stories.extend(part.element for part in document.part.package.parts if isinstance(part, HeaderPart))
    changed = False
    for story in stories:
        for paragraph in story.xpath("./w:p"):
            nodes = paragraph.xpath("./w:r/w:t | ./w:hyperlink/w:r/w:t")
            text = "".join(node.text or "" for node in nodes)
            if not text.startswith(LEGACY_CUSTOMER_MARKER):
                continue
            changed = True
            remaining = len(LEGACY_CUSTOMER_MARKER)
            for node in nodes:
                value = node.text or ""
                node.text = value[remaining:] or None
                remaining -= min(len(value), remaining)
                if remaining == 0:
                    break
            # Remove an empty stamp-only paragraph, retaining layout-bearing
            # breaks, drawings and any content the operator added.
            if not paragraph.xpath(
                ".//w:t[text()] | ./w:pPr/w:sectPr | ./w:*[not(self::w:r or self::w:pPr)]"
                " | ./w:r/w:*[not(self::w:t or self::w:rPr)]"
            ):
                story.remove(paragraph)
    if not changed:
        return content
    output = BytesIO()
    document.save(output)
    return output.getvalue()
