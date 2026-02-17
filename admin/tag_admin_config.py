from .catalog_constants import PAGE_SIZE_OPTIONS, TAG_ADMIN_PAGE_SIZE

TAG_GROUP_COLUMN_LIST = [
    "id",
    "title",
    "slug",
    "is_public",
    "color",
]
TAG_GROUP_COLUMN_LABELS = {
    "id": "ID",
    "title": "Название",
    "slug": "Slug",
    "is_public": "Публичная",
    "color": "Цвет",
}

TAG_COLUMN_LIST = [
    "id",
    "title",
    "is_public",
    "is_filter",
]
TAG_COLUMN_LABELS = {
    "id": "ID",
    "title": "Название",
    "is_public": "Публичный",
    "is_filter": "Фильтр",
}
TAG_PAGE_SIZE = TAG_ADMIN_PAGE_SIZE
TAG_PAGE_SIZE_OPTIONS = PAGE_SIZE_OPTIONS
