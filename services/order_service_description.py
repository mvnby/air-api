"""Keep frozen installation scope visible in customer documents."""

from typing import Any, Mapping


def service_line_document_title(
    link: Any, installation_descriptions: Mapping[int, str] | None = None,
) -> str:
    title = str(
        getattr(link, "title", None)
        or getattr(getattr(link, "service", None), "title", None)
        or "Услуга"
    )
    description = (installation_descriptions or {}).get(getattr(link, "id", None), "")
    return f"{title}\n{description}" if description else title
