from models.product import Product, ProductImage
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
