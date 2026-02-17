from markupsafe import Markup

from .catalog_constants import (
    GALLERY_STATUS_EMPTY_BADGE,
    GALLERY_STATUS_PRESENT_TEMPLATE,
    PRODUCT_AREA_SUFFIX,
    PRODUCT_EMPTY_PLACEHOLDER,
    PRODUCT_IMAGE_PREVIEW_STYLE,
)
from .formatters import format_tags_shared


def format_product_image(model, context):
    if model.main_image:
        url = model.main_image if model.main_image.startswith("/") else f"/{model.main_image}"
        return Markup(f'<img src="{url}" style="{PRODUCT_IMAGE_PREVIEW_STYLE}">')
    return ""


def format_product_title(model, context):
    title_html = f"<strong>{model.title}</strong>"
    tags_html = format_tags_shared(model, context, hide_group=True)
    return Markup(f'{title_html}<br><div class="tags__product_title">{tags_html}</div>')


def format_product_area(model, context):
    if model.area:
        return f"{model.area}{PRODUCT_AREA_SUFFIX}"
    return PRODUCT_EMPTY_PLACEHOLDER


def format_product_price(model, context):
    if model.price:
        return f"{model.price:,}".replace(",", " ")
    return PRODUCT_EMPTY_PLACEHOLDER


def format_product_gallery_status(model, context):
    if model.gallery_images:
        return Markup(GALLERY_STATUS_PRESENT_TEMPLATE.format(count=len(model.gallery_images)))
    return Markup(GALLERY_STATUS_EMPTY_BADGE)
