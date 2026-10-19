from models import FeatureBrandLink, FeatureProductLink, FeatureSeriesLink
from services.feature_resolver_service import FeatureResolverService


def test_series_owns_default_and_product_inherits_without_editor_roundtrip_change():
    brand = FeatureBrandLink(brand_id=1, feature_id=1, display_mode="icon")
    series = FeatureSeriesLink(series_id=1, feature_id=1)
    model = FeatureProductLink(product_id=1, feature_id=1)
    resolve = FeatureResolverService._display_mode
    assert resolve(None, None, brand) == "icon"
    assert resolve(model, series, brand) == "detailed"
    series.display_mode = "detailed"
    assert resolve(model, series, brand) == "detailed"
    series.display_mode = "compact"
    assert resolve(model, series, brand) == "compact"
    model.display_mode = "icon"
    assert resolve(model, series, brand) == "icon"
