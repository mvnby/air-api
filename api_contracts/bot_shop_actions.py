"""Staff shop commands take product identities; the API resolves commercial data."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BotShopLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=99)


class BotShopBasket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BotShopLine] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_products(self):
        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValueError("Модель указана больше одного раза.")
        return self


class BotShopOrderInput(BotShopBasket):
    idempotency_key: UUID
    prospect_type: Literal["individual", "company"]
    proposal_mode: Literal["bundle", "alternatives"]


class BotShopOrderRequest(BotShopOrderInput):
    telegram_id: int = Field(gt=0)
    expected_context_version: int = Field(ge=0)


class BotShopOrderResponse(BaseModel):
    id: int = Field(gt=0)


class BotShopOfferRequest(BotShopBasket):
    telegram_id: int = Field(gt=0)
    expected_context_version: int = Field(ge=0)
    request_id: UUID
    title: str = Field(min_length=1, max_length=120)


class BotShopOfferResponse(BaseModel):
    url: str
    expires_at: datetime
