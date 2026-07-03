import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts/check_media_cdn_db_urls.py"
SPEC = importlib.util.spec_from_file_location("check_media_cdn_db_urls", MODULE_PATH)
check_media_cdn_db_urls = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_media_cdn_db_urls
SPEC.loader.exec_module(check_media_cdn_db_urls)


def test_refs_from_order_meta_extracts_nested_object_storage_entries_only():
    refs = check_media_cdn_db_urls.refs_from_order_meta(
        121,
        {
            "telegram_attachments": [
                {"file_id": "legacy-only"},
                {
                    "storage_provider": "r2",
                    "url": "https://cdn.mvn.by/orders/121/telegram/photo/hash.jpg",
                    "raw_text": "must not be printed by checker",
                },
            ],
            "repair": {
                "nameplate_recognitions": [
                    {
                        "storage_provider": "local",
                        "url": "/media/orders/121/local.jpg",
                    },
                    {
                        "storage_provider": "s3_compatible",
                        "url": "https://cdn.mvn.by/orders/121/telegram/photo/other.jpg",
                    },
                ]
            },
        },
    )

    assert [(ref.source, ref.object_id, ref.storage_provider, ref.url) for ref in refs] == [
        (
            "order_technical_meta",
            "121",
            "r2",
            "https://cdn.mvn.by/orders/121/telegram/photo/hash.jpg",
        ),
        (
            "order_technical_meta",
            "121",
            "s3_compatible",
            "https://cdn.mvn.by/orders/121/telegram/photo/other.jpg",
        ),
    ]
    assert refs[0].field == "$.telegram_attachments[1]"


def test_validate_db_media_refs_requires_public_cdn_url_for_object_storage():
    refs = [
        check_media_cdn_db_urls.DbMediaRef(
            source="product_image_variant",
            object_id="1",
            field="original",
            storage_provider="r2",
            url="https://cdn.mvn.by/products/variants/original/hash.webp",
        ),
        check_media_cdn_db_urls.DbMediaRef(
            source="media_asset",
            object_id="2",
            field="original",
            storage_provider="r2",
            url=None,
        ),
        check_media_cdn_db_urls.DbMediaRef(
            source="order_technical_meta",
            object_id="121",
            field="$.telegram_attachments[0]",
            storage_provider="r2",
            url="https://example.test/orders/121/file.jpg",
        ),
    ]

    failures = check_media_cdn_db_urls.validate_db_media_refs(
        refs,
        expected_cdn_base="https://cdn.mvn.by",
        min_db_cdn_urls=2,
    )

    assert any("provider=r2 is missing public URL" in failure for failure in failures)
    assert any("url does not use https://cdn.mvn.by" in failure for failure in failures)
    assert any("only 1 DB CDN media urls found; expected at least 2" in failure for failure in failures)


def test_unique_db_cdn_urls_deduplicates_and_ignores_non_cdn_refs():
    refs = [
        check_media_cdn_db_urls.DbMediaRef("product_image_variant", "1", "original", "r2", "https://cdn.mvn.by/a.webp"),
        check_media_cdn_db_urls.DbMediaRef("product_image_variant", "2", "card", "r2", "https://cdn.mvn.by/a.webp"),
        check_media_cdn_db_urls.DbMediaRef("media_asset", "3", "original", "r2", "https://cdn.mvn.by/b.webp"),
        check_media_cdn_db_urls.DbMediaRef("media_asset", "4", "original", "r2", "https://example.test/c.webp"),
        check_media_cdn_db_urls.DbMediaRef("media_asset", "5", "original", "r2", None),
    ]

    urls = check_media_cdn_db_urls.unique_db_cdn_urls(
        refs,
        expected_cdn_base="https://cdn.mvn.by",
    )

    assert urls == ["https://cdn.mvn.by/a.webp", "https://cdn.mvn.by/b.webp"]
