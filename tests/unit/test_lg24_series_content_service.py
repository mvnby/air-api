from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import MediaAsset, ProductSeries
from services.lg24_series_content_service import (
    Lg24SeriesSeed,
    collect_feature_block_image_urls,
    detected_feature_slugs,
    extract_feature_blocks,
    extract_feature_gallery_images,
    extract_short_features,
    import_series_media_urls,
    resolve_or_import_series_media,
    remap_feature_block_image_urls,
    should_update_media_value,
    text_matches_series,
)
from services.media_library_service import StoredLibraryImage


@pytest.fixture
async def sqlite_session(tmp_path: Path):
    db_path = tmp_path / "lg24_series_content.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_extract_short_features_uses_feature_list_items_only():
    soup = _soup(
        """
        <div class="woocommerce-product-details__short-description">
          <ul class="feature-list">
            <li>Dual Inverter компрессор</li>
            <li>Wi-Fi и голосовое управление <img data-src="/wp-content/uploads/icon.jpg" /></li>
            <li>Dual Inverter компрессор</li>
          </ul>
        </div>
        """
    )

    assert extract_short_features(soup) == [
        "Dual Inverter компрессор",
        "Wi-Fi и голосовое управление",
    ]


def test_extract_feature_blocks_stops_before_next_page_section():
    soup = _soup(
        """
        <h2>Преимущества</h2>
        <div class="title"><h3>Gold Fin™</h3></div>
        <div class="copy font-regular">Защита теплообменника от коррозии.</div>
        <div class="title"><h3>Габаритные размеры</h3></div>
        <h2>Оплата и доставка</h2>
        <div class="title"><h3>Отзывы</h3></div>
        """
    )

    assert extract_feature_blocks(soup) == [
        {
            "title": "Gold Fin™",
            "text": "Защита теплообменника от коррозии.",
            "image_url": None,
            "icon": None,
            "footnote": None,
        }
    ]


def test_extract_feature_blocks_attaches_first_image_before_next_heading():
    soup = _soup(
        """
        <h2>Преимущества</h2>
        <div class="title"><h3>Gold Fin™</h3></div>
        <p>Защита теплообменника от коррозии.</p>
        <p><img src="data:image/svg+xml,placeholder" data-src="/wp-content/uploads/gold-fin.jpg" /></p>
        <div class="title"><h3>Бесшумная работа</h3></div>
        <p><img src="/wp-content/uploads/silent.jpg" /></p>
        <h2>Отзывы</h2>
        """
    )

    blocks = extract_feature_blocks(soup, "https://lg24.by/product/demo/")

    assert blocks[0]["image_url"] == "https://lg24.by/wp-content/uploads/gold-fin.jpg"
    assert blocks[1]["image_url"] == "https://lg24.by/wp-content/uploads/silent.jpg"


def test_extract_feature_gallery_images_ignores_lazy_placeholders():
    soup = _soup(
        """
        <h2>Преимущества</h2>
        <img src="data:image/svg+xml,placeholder" />
        <img data-src="/wp-content/uploads/feature.jpg" />
        <h2>Отзывы</h2>
        <img data-src="/wp-content/uploads/review.jpg" />
        """
    )

    assert extract_feature_gallery_images(soup, "https://lg24.by/product/demo/") == [
        "https://lg24.by/wp-content/uploads/feature.jpg"
    ]


def test_detected_feature_slugs_from_lg24_text():
    slugs = detected_feature_slugs(
        [
            "Технология Dual Inverter компрессор с 10-летней гарантией",
            "Технология UVnano уничтожает вирусы, плесень и бактерии с помощью УФ-лампы",
            "Wi-Fi и голосовое управление, мониторинг с помощью приложения LG SmartThinQ",
        ]
    )

    assert "dual-inverter" in slugs
    assert "uvnano" in slugs
    assert "lg-thinq" in slugs


def test_text_matches_series_by_slug_alias():
    seed = Lg24SeriesSeed(
        title="EVO Max",
        source_url="https://lg24.by/product-category/konditionery_dla_doma/evo_max/",
        match_slugs=("evo-max", "evomax"),
        tagline="",
        short_description="",
        description="",
        fallback_features=(),
    )

    assert text_matches_series(ProductSeries(title="LG EVO Max", slug="evomax"), seed)
    assert not text_matches_series(ProductSeries(title="LG ECO Smart", slug="eco-smart"), seed)


def test_feature_block_media_url_collection_and_remap():
    blocks = [
        {"title": "A", "image_url": "https://lg24.by/a.jpg#frag"},
        {"title": "B", "image_url": "https://lg24.by/a.jpg"},
        {"title": "C", "image_url": "https://lg24.by/c.jpg"},
        {"title": "D", "image_url": None},
    ]

    assert collect_feature_block_image_urls(blocks) == [
        "https://lg24.by/a.jpg",
        "https://lg24.by/c.jpg",
    ]

    remapped = remap_feature_block_image_urls(
        blocks,
        {
            "https://lg24.by/a.jpg": "/media/library/original/a.webp",
            "https://lg24.by/c.jpg": "/media/library/original/c.webp",
        },
    )

    assert remapped[0]["image_url"] == "/media/library/original/a.webp"
    assert remapped[1]["image_url"] == "/media/library/original/a.webp"
    assert remapped[2]["image_url"] == "/media/library/original/c.webp"
    assert remapped[3]["image_url"] is None


def test_import_media_updates_existing_external_media_values_without_overwrite():
    assert should_update_media_value(
        ["https://lg24.by/a.jpg"],
        ["/media/library/original/a.webp"],
        overwrite=False,
        import_media=True,
    )
    assert not should_update_media_value(
        ["/media/library/original/a.webp"],
        ["/media/library/original/a.webp"],
        overwrite=False,
        import_media=True,
    )
    assert not should_update_media_value(
        ["https://lg24.by/a.jpg"],
        ["/media/library/original/a.webp"],
        overwrite=False,
        import_media=False,
    )


@pytest.mark.asyncio
async def test_resolve_or_import_series_media_creates_and_reuses_asset(sqlite_session, monkeypatch):
    calls = {"download": 0, "store": 0}

    async def fake_download(url: str):
        calls["download"] += 1
        return b"image-content", "feature.jpg"

    async def fake_store(content: bytes, *, variant_type: str):
        calls["store"] += 1
        assert content == b"image-content"
        assert variant_type == "original"
        return StoredLibraryImage(
            url="/media/library/original/feature.webp",
            path="media/library/original/feature.webp",
            content_hash="hash",
            width=1600,
            height=900,
            size_bytes=1234,
        )

    monkeypatch.setattr(
        "services.lg24_series_content_service.MediaLibraryService._download_remote_image",
        staticmethod(fake_download),
    )
    monkeypatch.setattr(
        "services.lg24_series_content_service.MediaLibraryService._store_image",
        staticmethod(fake_store),
    )

    first = await resolve_or_import_series_media(
        sqlite_session,
        source_url="https://lg24.by/wp-content/uploads/feature.jpg#fragment",
        title="LG EVO Max: изображение 1",
    )
    second = await resolve_or_import_series_media(
        sqlite_session,
        source_url="https://lg24.by/wp-content/uploads/feature.jpg",
        title="LG EVO Max: изображение 1",
    )

    assert first is not None
    assert second is not None
    assert first.url == "/media/library/original/feature.webp"
    assert first.created is True
    assert second.url == first.url
    assert second.created is False
    assert calls == {"download": 1, "store": 1}

    assets = (await sqlite_session.execute(select(MediaAsset))).scalars().all()
    assert len(assets) == 1
    assert assets[0].original_url == "https://lg24.by/wp-content/uploads/feature.jpg"
    assert assets[0].kind == "brand"
    assert assets[0].tags == ["lg", "series", "feature", "promo"]


@pytest.mark.asyncio
async def test_import_series_media_urls_dry_run_maps_existing_assets(sqlite_session):
    sqlite_session.add(
        MediaAsset(
            title="Existing LG promo",
            kind="brand",
            variant_type="original",
            url="/media/library/original/existing.webp",
            original_url="https://lg24.by/wp-content/uploads/existing.jpg",
            mime_type="image/webp",
            storage_provider="r2",
            processing_status="ready",
        )
    )
    await sqlite_session.flush()

    result = await import_series_media_urls(
        sqlite_session,
        urls=[
            "https://lg24.by/wp-content/uploads/existing.jpg",
            "https://lg24.by/wp-content/uploads/new.jpg",
        ],
        execute=False,
        title_prefix="LG Test",
    )

    assert result["planned"] == 2
    assert result["imported"] == 0
    assert result["reused"] == 1
    assert result["failed"] == []
    assert result["map"] == {
        "https://lg24.by/wp-content/uploads/existing.jpg": "/media/library/original/existing.webp"
    }
