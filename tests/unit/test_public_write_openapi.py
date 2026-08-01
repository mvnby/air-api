from fastapi import FastAPI

from routers.api_leads import router as leads_router
from routers.api_orders import router as orders_router


def test_public_write_openapi_declares_gateway_and_command_errors_exactly():
    app = FastAPI()
    app.include_router(leads_router, prefix="/api")
    app.include_router(orders_router, prefix="/api")
    paths = app.openapi()["paths"]
    write_paths = (
        "/api/v1/orders",
        "/api/v1/leads/contact",
        "/api/v1/leads/product-availability",
        "/api/v1/leads/installation-estimate",
        "/api/v1/leads/repair-diagnostic",
    )

    for path in write_paths:
        responses = paths[path]["post"]["responses"]
        assert {"400", "401", "409", "413", "503"}.issubset(responses)
        for status in ("400", "401", "413", "503"):
            assert responses[status]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/PublicWriteRequestErrorResponse"
            }
        assert "Retry-After" in responses["503"]["headers"]

    for path in write_paths[1:]:
        conflict = paths[path]["post"]["responses"]["409"]
        assert conflict["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/PublicWriteIdempotencyErrorResponse"
        }

    checkout_conflict = paths[write_paths[0]]["post"]["responses"]["409"]
    assert {
        item["$ref"]
        for item in checkout_conflict["content"]["application/json"]["schema"][
            "anyOf"
        ]
    } == {
        "#/components/schemas/PublicOrderPricingErrorResponse",
        "#/components/schemas/PublicWriteIdempotencyErrorResponse",
    }
