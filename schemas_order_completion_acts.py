"""Shared commands for a standard completion act covering selected order sites."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from models.common import DocumentRoleType
from schemas_business_document_terms import ActTermsPayload
from schemas_connector_mcp import ConnectorInput, WriteInput


PositiveId = Annotated[int, Field(gt=0)]


class OrderCompletionActSourceInput(ConnectorInput):
    order_id: PositiveId
    proposal_id: PositiveId


class OrderCompletionActSource(OrderCompletionActSourceInput):
    proposal_version: str


class PrepareOrderCompletionActPayload(WriteInput):
    site_ids: list[PositiveId] = Field(min_length=1, max_length=100)
    proposal_id: PositiveId
    expected_proposal_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    legal_entity_id: PositiveId
    issue_date: date
    issue_city: str | None = Field(default=None, max_length=160)
    document_role_type: DocumentRoleType | None = None
    base_document_id: PositiveId | None = None
    base_customer_contract_id: PositiveId | None = None
    act_terms: ActTermsPayload
    template_id: PositiveId | None = None
    scope_service_line_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    scope_service_line_quantities: dict[PositiveId, PositiveId] = Field(default_factory=dict, max_length=500)
    scope_product_line_ids: list[PositiveId] = Field(default_factory=list, max_length=500)
    scope_product_line_quantities: dict[PositiveId, PositiveId] = Field(default_factory=dict, max_length=500)
    replaces_document_id: PositiveId | None = None
    expected_document_revision: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_scope(self):
        if (self.base_document_id is None) == (self.base_customer_contract_id is None):
            raise ValueError("Выберите одно основание для акта")
        if (self.replaces_document_id is None) != (self.expected_document_revision is None):
            raise ValueError("При исправлении акта укажите его актуальную версию")
        if len(set(self.site_ids)) != len(self.site_ids):
            raise ValueError("Укажите каждый объект один раз")
        for ids, quantities in (
            (self.scope_service_line_ids, self.scope_service_line_quantities),
            (self.scope_product_line_ids, self.scope_product_line_quantities),
        ):
            if len(set(ids)) != len(ids) or not quantities.keys() <= set(ids):
                raise ValueError("Количество можно указать один раз только для выбранной строки предложения")
        return self


class PrepareOrderCompletionActInput(PrepareOrderCompletionActPayload):
    order_id: PositiveId


class OrderCompletionActPrepared(BaseModel):
    order_id: int
    site_ids: list[int]
    proposal_id: int
    document_id: int
    status: str
    revision: str
    manager_url: str
