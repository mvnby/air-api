from models.product import Product, ProductImage, Tag, TagGroup
from services.catalog_quality_filters import (
    build_builtin_view_counts,
    build_groups,
    classify_product,
    enrich_work_priority,
    filter_dimension_rows,
    sort_rows,
)
from services.catalog_quality_service import (
    CatalogQualityService,
    ImageInfo,
    _image_urls_from_product,
)


def test_image_urls_from_product_deduplicates_main_json_and_gallery():
    product = Product(title="TCL Test", slug="tcl-test", price=1000)
    product.main_image = "/media/products/main.webp"
    product.images = [
        "/media/products/main.webp",
        {"url": "/media/products/side.webp"},
        {"src": "/media/products/front.webp"},
    ]
    product.gallery_images = [
        ProductImage(product_id=1, url="/media/products/side.webp"),
        ProductImage(product_id=1, url="/media/products/remote.webp"),
    ]

    assert _image_urls_from_product(product) == [
        "/media/products/main.webp",
        "/media/products/side.webp",
        "/media/products/front.webp",
        "/media/products/remote.webp",
    ]


def test_collect_issues_flags_single_low_resolution_product_media():
    product = Product(title="Onliner low", slug="onliner-low", price=1200)
    product.main_image = "/media/products/small.webp"
    product.brand_id = 1
    product.series_id = 2
    product.area = 25
    product.power_cooling = 2.6
    issues = CatalogQualityService._collect_issues(
        product=product,
        specs={},
        image_infos=[ImageInfo(url=product.main_image, width=220, height=180, source="file")],
        main_image_info=ImageInfo(url=product.main_image, width=220, height=180, source="file"),
        available_qty=3,
        active_mapping_count=1,
    )

    codes = {issue.code for issue in issues}
    assert {"single_image", "low_resolution_main_image", "all_images_low_resolution"}.issubset(codes)


def test_collect_issues_flags_supplier_and_identity_gaps():
    product = Product(title="Draft", slug="draft", price=0)
    issues = CatalogQualityService._collect_issues(
        product=product,
        specs={},
        image_infos=[],
        main_image_info=None,
        available_qty=0,
        active_mapping_count=0,
    )

    codes = {issue.code for issue in issues}
    assert {
        "missing_brand",
        "missing_series",
        "missing_main_image",
        "missing_price",
        "missing_supplier_mapping",
        "out_of_stock",
    }.issubset(codes)


def test_classify_product_uses_normalized_taxonomy_not_title():
    category_group = TagGroup(id=1, title="Категория", slug="category")
    type_group = TagGroup(id=2, title="Тип", slug="type")
    category = Tag(id=3, title="Полупромышленные", slug="cat-industrial", group=category_group)
    wrong_title_type = Tag(id=4, title="Настенный", slug="wall", group=type_group)
    product = Product(
        title="Бытовой Multi Pro в названии не должен влиять",
        slug="normalized-semi",
        price=1000,
        specs={"indoor_type": "кассетный"},
        tags=[category, wrong_title_type],
    )

    assert classify_product(product) == (
        "cat-industrial",
        "Полупромышленное",
        "cassette",
        "Кассетные",
    )


def test_classify_multi_components_does_not_treat_generic_type_as_kit():
    category_group = TagGroup(id=1, title="Категория", slug="category")
    type_group = TagGroup(id=2, title="Тип", slug="type")
    category = Tag(id=3, title="Мульти-сплит", slug="cat-multi", group=category_group)
    indoor_type = Tag(id=4, title="Настенный", slug="wall", group=type_group)

    indoor = Product(
        title="Legacy title must not be parsed",
        slug="multi-indoor",
        price=1000,
        specs={"type": "мульти-сплит-система", "indoor_type": "настенный"},
        tags=[category, indoor_type],
    )
    incomplete = Product(
        title="Внутренний блок только в заголовке",
        slug="multi-unknown",
        price=1000,
        specs={"type": "мульти-сплит-система"},
        tags=[category],
    )
    kit = Product(
        title="Комплект",
        slug="multi-kit",
        price=1000,
        specs={
            "type": "мульти-сплит-система",
            "includes_indoor_unit": True,
            "includes_outdoor_unit": True,
        },
        tags=[category],
    )

    assert classify_product(indoor)[2:] == ("multi-indoor", "Внутренние блоки")
    assert classify_product(incomplete)[2:] == (None, None)
    assert classify_product(kit)[2:] == ("multi-kit", "Комплекты")


def test_dimension_filters_use_selected_supplier_stock_and_fixable_issues():
    rows = [
        {
            "product_id": 1,
            "equipment_type": "cat-household",
            "brand_id": 10,
            "series_id": None,
            "is_published": True,
            "available_qty": 5,
            "score": 72,
            "issues": [{"category": "media", "severity": "critical"}],
            "suppliers": [
                {"supplier_id": 20, "qty": 0},
                {"supplier_id": 21, "qty": 5},
            ],
        },
        {
            "product_id": 2,
            "equipment_type": "cat-industrial",
            "brand_id": 10,
            "series_id": 30,
            "is_published": False,
            "available_qty": 0,
            "score": 90,
            "issues": [{"category": "commerce", "severity": "info"}],
            "suppliers": [],
        },
    ]
    for row in rows:
        enrich_work_priority(row)

    assert filter_dimension_rows(rows, supplier_id=20, supplier_state="in_stock") == []
    assert [row["product_id"] for row in filter_dimension_rows(rows, supplier_id=21, supplier_state="in_stock")] == [1]
    assert [row["product_id"] for row in filter_dimension_rows(rows, series_state="missing", only_fixable=True)] == [1]
    assert rows[0]["work_priority"] == "high"
    assert rows[1]["work_priority"] == "low"


def test_priority_sort_and_series_groups_are_transparent():
    rows = [
        {
            "product_id": 1,
            "title": "Good",
            "series_id": 100,
            "series_title": "Elite",
            "score": 92,
            "work_priority": "medium",
            "work_priority_score": 20,
            "critical_issue_count": 0,
            "issues": [],
        },
        {
            "product_id": 2,
            "title": "Needs work",
            "series_id": 100,
            "series_title": "Elite",
            "score": 60,
            "work_priority": "high",
            "work_priority_score": 180,
            "critical_issue_count": 1,
            "issues": [{"category": "media", "severity": "critical"}],
        },
    ]

    assert [row["product_id"] for row in sort_rows(rows, "priority")] == [2, 1]
    assert build_groups(rows, "series") == [
        {
            "key": "series:100",
            "label": "Elite",
            "count": 2,
            "average_score": 76,
            "critical_products": 1,
            "media_problem_products": 1,
            "spec_problem_products": 0,
        }
    ]


def test_priority_sort_keeps_medium_ahead_of_low_even_with_a_lower_numeric_score():
    rows = [
        {"product_id": 1, "title": "Deferred", "score": 30, "work_priority": "low", "work_priority_score": 500},
        {"product_id": 2, "title": "Current", "score": 70, "work_priority": "medium", "work_priority_score": 80},
    ]

    assert [row["product_id"] for row in sort_rows(rows, "priority")] == [2, 1]


def test_builtin_view_counts_use_the_same_filters_as_workspace_presets():
    rows = [
        {
            "product_id": 1,
            "equipment_type": "cat-household",
            "series_id": None,
            "is_published": True,
            "available_qty": 4,
            "score": 40,
            "issues": [{"category": "media", "severity": "critical"}],
            "suppliers": [],
        },
        {
            "product_id": 2,
            "equipment_type": "cat-household",
            "series_id": None,
            "is_published": False,
            "available_qty": 0,
            "score": 80,
            "issues": [{"category": "supplier", "severity": "warning"}],
            "suppliers": [],
        },
    ]
    for row in rows:
        enrich_work_priority(row)

    assert build_builtin_view_counts(rows) == {
        "critical-published": 1,
        "stock-media": 1,
        "household-no-series": 2,
        "supplier-unmapped": 1,
    }
