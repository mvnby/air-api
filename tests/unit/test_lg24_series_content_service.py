from bs4 import BeautifulSoup

from models import ProductSeries
from services.lg24_series_content_service import (
    Lg24SeriesSeed,
    detected_feature_slugs,
    extract_feature_blocks,
    extract_feature_gallery_images,
    extract_short_features,
    text_matches_series,
)


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
