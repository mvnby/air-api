from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CatalogBulkChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["relations", "specs", "features", "publication", "category"]
    brand_id: int | None = Field(default=None, gt=0)
    series_id: int | None = Field(default=None, gt=0)
    specs: dict[str, Any] = Field(default_factory=dict, max_length=30)
    spec_mode: Literal["set", "fill_empty", "remove"] = "set"
    feature_ids: list[int] = Field(default_factory=list, max_length=50)
    feature_mode: Literal["add", "hide", "inherit"] = "add"
    is_published: bool | None = None
    category: Literal["cat-household", "cat-multi", "cat-industrial"] | None = None

    @model_validator(mode="after")
    def valid_operation(self):
        if self.kind == "publication" and self.is_published is None:
            raise ValueError("Укажите состояние публикации")
        if self.kind == "specs" and not self.specs:
            raise ValueError("Укажите характеристики")
        if self.kind == "features" and not self.feature_ids:
            raise ValueError("Выберите фичи")
        if self.kind == "relations" and not {"brand_id", "series_id"}.issubset(self.model_fields_set):
            raise ValueError("Явно выберите бренд и серию, включая очистку")
        if self.kind == "category" and "category" not in self.model_fields_set:
            raise ValueError("Явно выберите категорию или автоматическое определение")
        return self


class CatalogBulkPreviewRequest(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=500)
    change: CatalogBulkChange


class CatalogBulkPreviewItem(BaseModel):
    product_id: int
    title: str
    before: dict[str, Any]
    after: dict[str, Any]
    changed: bool


class CatalogBulkPreviewResponse(BaseModel):
    token: str
    items: list[CatalogBulkPreviewItem]
    changed_count: int
    expires_in_seconds: int = 900


class CatalogBulkApplyRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200000)


class CatalogBulkApplyResponse(BaseModel):
    updated: int
    product_ids: list[int]
