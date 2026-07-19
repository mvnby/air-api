"""Shared mappers for Product -> dict payloads used across services."""

from typing import Any, Dict

from models import Product
from services.product_serialization import sanitize_specs, to_web_path


def map_product_to_dict(
    product: Product,
    *,
    include_tag_groups: bool = False,
    include_media: bool = False,
    sanitize_specs_payload: bool = False,
) -> Dict[str, Any]:
    data = product.model_dump()
    data.pop("area", None)
    tags = list(product.tags or [])
    data["categories"] = [tag.title for tag in tags]

    tags_data = []
    for tag in tags:
        tag_dict = tag.model_dump()
        if include_tag_groups and tag.group:
            tag_dict["group"] = tag.group.model_dump()
        tags_data.append(tag_dict)
    data["tags"] = tags_data

    if include_media:
        if data.get("main_image") and not data["main_image"].startswith("/"):
            data["main_image"] = "/" + data["main_image"]

        gallery = sorted(
            list(product.gallery_images or []),
            key=lambda item: (item.is_installation_photo, item.id),
        )

        data["images"] = [to_web_path(img.url) for img in gallery]
        data["gallery_images"] = [
            {
                **img.model_dump(),
                "url": to_web_path(img.url),
            }
            for img in gallery
        ]
        data["manuals"] = [
            {
                "id": item.id,
                "kind": item.kind,
                "title": item.title,
                "url": item.url,
                "source": item.source,
            }
            for item in (product.attachments or [])
            if item.kind == "manual"
        ]

    if sanitize_specs_payload:
        data["specs"] = sanitize_specs(data.get("specs"))

    return data
