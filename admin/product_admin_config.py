from wtforms import FileField, TextAreaField
from wtforms.validators import DataRequired

from .catalog_constants import (
    PAGE_SIZE_OPTIONS,
    PRODUCT_ADMIN_PAGE_SIZE,
    PRODUCT_IMAGES_READONLY_DESCRIPTION,
    PRODUCT_MAIN_IMAGE_UPLOAD_LABEL,
    PRODUCT_SLUG_DESCRIPTION,
    PRODUCT_SLUG_LABEL,
)

PRODUCT_COLUMN_LIST = [
    "id",
    "formatted_title",
    "price",
    "main_image",
    "gallery_status",
    "formatted_area",
    "is_published",
]
PRODUCT_SEARCHABLE_COLUMNS = ["title", "description"]
PRODUCT_DEFAULT_SORT = ("created_at", True)
PRODUCT_EDITABLE_COLUMNS = ["is_published"]
PRODUCT_PAGE_SIZE = PRODUCT_ADMIN_PAGE_SIZE
PRODUCT_PAGE_SIZE_OPTIONS = PAGE_SIZE_OPTIONS

PRODUCT_FORM_COLUMNS = [
    "title",
    "slug",
    "description",
    "price",
    "old_price",
    "area",
    "is_inverter",
    "power_cooling",
    "main_image",
    "images",
    "tags",
    "specs",
    "is_published",
    "source_url",
]
PRODUCT_FORM_AJAX_REFS = {
    "tags": {
        "fields": ["title", "slug"],
        "order_by": "title",
        "placeholder": "Начните вводить характеристику...",
        "minimum_input_length": 0,
    }
}
PRODUCT_FORM_OVERRIDES = {
    "description": TextAreaField,
    "images": TextAreaField,
}
PRODUCT_FORM_EXTRA_FIELDS = {
    "main_image_file": FileField(PRODUCT_MAIN_IMAGE_UPLOAD_LABEL),
}
PRODUCT_FORM_EDIT_RULES = [
    "title",
    "slug",
    "description",
    "area",
    "is_inverter",
    "power_cooling",
    "price",
    "old_price",
    "source_url",
    "is_published",
    "main_image",
    "main_image_file",
    "images",
    "tags",
    "specs",
]

PRODUCT_COLUMN_LABELS = {
    "formatted_title": "Товар",
    "formatted_area": "Площадь",
    "price": "Цена",
    "main_image": "Фото",
    "gallery_status": "Галерея",
    "is_published": "Включён",
}
PRODUCT_FORM_ARGS = {
    "slug": {
        "validators": [DataRequired()],
        "label": PRODUCT_SLUG_LABEL,
        "description": PRODUCT_SLUG_DESCRIPTION,
    },
    "images": {
        "render_kw": {"readonly": True, "style": "background-color: #f8f9fa;"},
        "description": PRODUCT_IMAGES_READONLY_DESCRIPTION,
    },
}
