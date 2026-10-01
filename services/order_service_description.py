"""Keep frozen installation scope visible in customer documents."""

from typing import Any, Mapping


def service_line_description(link: Any, presentation: Mapping | None = None) -> str | None:
    """Prefer an explicit commercial description, otherwise retain frozen evidence."""
    description = getattr(link, "description", None)
    if description is not None:
        return description
    presentation = presentation or {}
    if presentation.get("description") is not None:
        return presentation["description"]
    rows = []
    for line in presentation.get("installation_display_lines") or []:
        label = line["title"]
        if line.get("quantity", 1) != 1:
            label += f" × {line['quantity']}"
        if line.get("description"):
            label += f": {line['description']}"
        rows.append(label)
    return "\n".join(rows) or None


def service_line_document_title(
    link: Any, installation_descriptions: Mapping[int, str] | None = None,
) -> str:
    title = str(
        getattr(link, "title", None)
        or getattr(getattr(link, "service", None), "title", None)
        or "Услуга"
    )
    description = getattr(link, "description", None)
    if description is None:
        description = (installation_descriptions or {}).get(getattr(link, "id", None), "")
    return f"{title}\n{description}" if description else title
