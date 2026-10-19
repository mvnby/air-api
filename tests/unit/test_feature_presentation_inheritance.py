from models import FeatureBrandLink, FeatureProductLink, FeatureSeriesLink
from services.feature_resolver_service import FeatureResolverService


def test_series_editor_keeps_unconfigured_modes_distinct_from_public_presentation():
    from models import Feature, ProductSeries
    from services.manager_brand_service import ManagerBrandService
    from services.product_series_payloads import serialize_series_brand_features

    feature = Feature(id=1, slug="test", name="Test", category_id=1)
    link = FeatureSeriesLink(series_id=1, feature_id=1)
    link.__dict__["feature"] = feature
    series = ProductSeries(id=1, brand_id=1, title="Series", slug="series")
    series.__dict__["feature_links"] = [link]
    serialize = ManagerBrandService._serialize_series_feature_link
    for mode, featured, effective in [(None, False, "icon"), (None, True, "detailed"), ("compact", True, "compact")]:
        link.display_mode, link.is_featured = mode, featured
        item = serialize(link, feature)
        assert item["display_mode"] == effective
        assert item["_assignment_display_mode"] == mode
        manager = ManagerBrandService._serialize_series(series, brand_features=[item])
        assert manager["feature_assignments"][0]["display_mode"] == mode
        assert serialize_series_brand_features(series)[0].display_mode == effective


def test_series_owns_default_and_product_inherits_without_editor_roundtrip_change():
    brand = FeatureBrandLink(brand_id=1, feature_id=1, display_mode="icon")
    series = FeatureSeriesLink(series_id=1, feature_id=1)
    model = FeatureProductLink(product_id=1, feature_id=1)
    resolve = FeatureResolverService._display_mode
    assert resolve(None, None, brand) == "icon"
    assert resolve(model, series, brand) == "icon"
    series.display_mode = "detailed"
    assert resolve(model, series, brand) == "detailed"
    series.display_mode = "compact"
    assert resolve(model, series, brand) == "compact"
    model.display_mode = "icon"
    assert resolve(model, series, brand) == "icon"


def test_unconfigured_and_derived_features_use_the_compact_default():
    resolve = FeatureResolverService._display_mode
    assert resolve(None, None, None) == "icon"
    derived = FeatureProductLink(
        product_id=1, feature_id=1, source="derived", display_mode="detailed",
    )
    assert resolve(derived, None, None) == "icon"


def test_featured_series_default_is_rich_and_explicit_formats_still_win():
    series = FeatureSeriesLink(series_id=1, feature_id=1, is_featured=True)
    resolve = FeatureResolverService._display_mode
    assert resolve(None, series, None) == "detailed"
    series.display_mode = "compact"
    assert resolve(None, series, None) == "compact"
    series.display_mode = "icon"
    assert resolve(None, series, None) == "icon"
    model = FeatureProductLink(product_id=1, feature_id=1, display_mode="detailed")
    assert resolve(model, series, None) == "detailed"
