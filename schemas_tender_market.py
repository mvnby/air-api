"""Contract with the scoped public procurement feed."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from schemas_tender_search import TenderLotMatch


class MarketPublicationInput(BaseModel):
    source: Literal["goszakupki_by", "gias_by", "icetrade_by", "butb_by"]
    external_id: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=1, max_length=2048)
    canonical_url: str | None = Field(default=None, max_length=2048)
    title: str = Field(min_length=1, max_length=1000)
    active: bool
    deadline_at: AwareDatetime | None = None
    published_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    lots: list[dict] = Field(default_factory=list, max_length=20)
    lot_inventory_complete: bool = False


class MarketPageInput(BaseModel):
    items: list[dict] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=2048)
    has_more: bool

    @model_validator(mode="after")
    def validate_cursor(self):
        if self.has_more != (self.next_cursor is not None):
            raise ValueError("Market page has inconsistent cursor state")
        return self


class TenderMarketProfileMatch(BaseModel):
    name: str
    result: TenderLotMatch
    lots: list[TenderLotMatch]


class TenderMarketItem(BaseModel):
    id: int
    title: str
    source: str
    source_url: str
    deadline_at: AwareDatetime | None = None
    profiles: list[TenderMarketProfileMatch]


class TenderMarketResults(BaseModel):
    items: list[TenderMarketItem]
    next_before_id: int | None = None
    settings_version: int
    profile_names: list[str]
    last_sync_at: AwareDatetime | None = None
    syncing: bool = False
