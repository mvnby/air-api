from sqladmin import ModelView
from sqlalchemy.orm import selectinload

from models import Product, Tag, TagGroup
from .catalog_constants import (
    PAGE_SIZE_OPTIONS,
    TAG_ADMIN_PAGE_SIZE,
)
from .product_admin_config import (
    PRODUCT_COLUMN_LABELS,
    PRODUCT_COLUMN_LIST,
    PRODUCT_DEFAULT_SORT,
    PRODUCT_EDITABLE_COLUMNS,
    PRODUCT_FORM_AJAX_REFS,
    PRODUCT_FORM_ARGS,
    PRODUCT_FORM_COLUMNS,
    PRODUCT_FORM_EDIT_RULES,
    PRODUCT_FORM_EXTRA_FIELDS,
    PRODUCT_FORM_OVERRIDES,
    PRODUCT_PAGE_SIZE,
    PRODUCT_PAGE_SIZE_OPTIONS,
    PRODUCT_SEARCHABLE_COLUMNS,
)
from .formatters import format_tags_shared
from .product_admin_helpers import (
    build_tag_filter_subquery,
    ensure_slug,
    extract_uploaded_main_image,
    parse_tag_ids,
    save_new_product_main_image,
    set_existing_product_main_image,
)
from .product_formatters import (
    format_product_area,
    format_product_gallery_status,
    format_product_image,
    format_product_price,
    format_product_title,
)


class ProductAdmin(ModelView, model=Product):
    name = "Товар"
    name_plural = "Товары"
    icon = "fa-solid fa-snowflake"
    
    list_template = "product_list.html"
    edit_template = "sqladmin/product_edit.html"
    
    # --- КОЛОНКИ ---
    column_list = PRODUCT_COLUMN_LIST
    column_searchable_list = PRODUCT_SEARCHABLE_COLUMNS
    column_default_sort = PRODUCT_DEFAULT_SORT
    column_editable_list = PRODUCT_EDITABLE_COLUMNS
    page_size = PRODUCT_PAGE_SIZE
    page_size_options = PRODUCT_PAGE_SIZE_OPTIONS
    
    # --- ФОРМА: Порядок полей ---
    form_columns = PRODUCT_FORM_COLUMNS

    # --- AJAX для M2M: SQLAdmin сам создаст Select2 виджет ---
    form_ajax_refs = PRODUCT_FORM_AJAX_REFS
    
    # --- Оверрайды для НЕ-relationship полей ---
    form_overrides = PRODUCT_FORM_OVERRIDES
    
    # --- Extra fields (только для файла!) ---
    form_extra_fields = PRODUCT_FORM_EXTRA_FIELDS

    form_edit_rules = PRODUCT_FORM_EDIT_RULES
    form_create_rules = form_edit_rules
    
    # --- Eager loading для M2M + tag filtering ---
    def list_query(self, request):
        query = super().list_query(request)
        query = query.options(
            selectinload(Product.tags).selectinload(Tag.group),
            selectinload(Product.gallery_images)
        )

        tag_ids = parse_tag_ids(request)
        if tag_ids:
            # AND logic: product must have ALL selected tags
            tag_subquery = build_tag_filter_subquery(tag_ids)
            query = query.where(Product.id.in_(tag_subquery))

        return query
    
    def detail_query(self, request):
        query = super().detail_query(request)
        return query.options(selectinload(Product.tags).selectinload(Tag.group))

    def edit_query(self, request):
        query = super().edit_query(request)
        return query.options(selectinload(Product.tags).selectinload(Tag.group))

    # --- Scaffold form: добавляем только file field ---
    async def scaffold_form(self, *args, **kwargs):
        form_class = await super().scaffold_form(*args, **kwargs)
        form_class.main_image_file = self.form_extra_fields["main_image_file"]
        return form_class


    column_formatters = {
        "main_image": format_product_image,
        "formatted_title": format_product_title,
        "formatted_area": format_product_area,
        "price": format_product_price,
        "gallery_status": format_product_gallery_status,
    }
    
    column_labels = PRODUCT_COLUMN_LABELS
    
    # Make legacy images field read-only
    form_args = PRODUCT_FORM_ARGS

    # --- Сохранение: обработка файла через ProductService ---
    async def on_model_change(self, data, model, is_created, request):
        form = await request.form()
        upload = extract_uploaded_main_image(form)
        data.pop("main_image_file", None)
        ensure_slug(data)

        if not upload:
            await super().on_model_change(data, model, is_created, request)
            return

        if is_created:
            await super().on_model_change(data, model, is_created, request)
            await save_new_product_main_image(model, upload)
            return

        await set_existing_product_main_image(data, model, upload)
        await super().on_model_change(data, model, is_created, request)


class TagGroupAdmin(ModelView, model=TagGroup):
    name = "Группа тегов"
    name_plural = "Группы тегов"
    icon = "fa-solid fa-layer-group"
    column_list = [TagGroup.id, TagGroup.title, TagGroup.slug, TagGroup.is_public, TagGroup.color]
    column_labels = {
        "id": "ID",
        "title": "Название",
        "slug": "Slug",
        "is_public": "Публичная",
        "color": "Цвет"
    }
    column_details_list = "__all__"
    form_columns = "__all__"


class TagAdmin(ModelView, model=Tag):
    name = "Тег"
    name_plural = "Теги"
    icon = "fa-solid fa-tag"
    column_list = [Tag.id, Tag.title, Tag.is_public, Tag.is_filter]
    column_labels = {
        "id": "ID",
        "title": "Название",
        "is_public": "Публичный",
        "is_filter": "Фильтр"
    }
    page_size = TAG_ADMIN_PAGE_SIZE
    page_size_options = PAGE_SIZE_OPTIONS
    column_details_list = "__all__"

    form_columns = "__all__"
    
    column_formatters = {
        Tag.title: format_tags_shared
    }

    def list_query(self, request):
        query = super().list_query(request)
        return query.options(selectinload(self.model.group))
