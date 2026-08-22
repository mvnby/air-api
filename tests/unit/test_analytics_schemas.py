import pytest
from pydantic import ValidationError

from schemas_analytics import GoogleAdsAuthorizationPayload


def test_google_ads_customer_ids_are_normalized_and_required():
    payload = GoogleAdsAuthorizationPayload(
        customer_id="123-456-7890",
        login_customer_id="098-765-4321",
    )

    assert payload.customer_id == "1234567890"
    assert payload.login_customer_id == "0987654321"

    with pytest.raises(ValidationError):
        GoogleAdsAuthorizationPayload(customer_id="-")
