import pytest
from pydantic import ValidationError

from schemas_storefront_settings import StorefrontSettingsPayload, StorefrontSiteSettings, default_service_directions


@pytest.mark.parametrize("url", ["javascript:alert(1)", "https://t.me.evil.test/support", "https://user:password@t.me/support", "https://t.me/support?unexpected=value", "https://t.me/support?start=a&start=b", "https://t.me/support#other"])
def test_support_contact_rejects_unsafe_or_unrelated_destinations(url):
    with pytest.raises(ValidationError):
        StorefrontSiteSettings(display_name="Partner", support_telegram_url=url)


def test_public_contact_validation_and_explicit_directions():
    assert StorefrontSiteSettings(display_name="Partner", email=" INFO@EXAMPLE.COM ").email == "info@example.com"
    valid = {"site": {"display_name": "Partner"}, "services": [item.model_dump() for item in default_service_directions(enabled=False)], "version": 0}
    assert StorefrontSettingsPayload.model_validate(valid).version == 0
    valid["services"][0] = valid["services"][1]
    with pytest.raises(ValidationError):
        StorefrontSettingsPayload.model_validate(valid)
