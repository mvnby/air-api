"""Explicit existing-customer service-order creation for the MCP boundary."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schemas_connector_mcp import WriteInput
from services.order_scenarios import resolve_scenario


class ServiceOrderCreateInput(WriteInput):
    customer_id: int = Field(gt=0)
    workflow_type: Literal["repair", "service_work"]
    service_type: Literal["repair", "install_only", "pre_install", "dismantling"] | None = None
    incoming_id: int | None = Field(default=None, gt=0)
    expected_incoming_version: int | None = Field(default=None, ge=1)
    request_text: str | None = Field(default=None, max_length=20000)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    customer_branch_id: int | None = Field(default=None, gt=0)
    address: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_creation(self):
        resolve_scenario(workflow_type=self.workflow_type, service_type=self.service_type)
        if self.incoming_id is not None and self.expected_incoming_version is None:
            raise ValueError("expected_incoming_version is required for qualification")
        if self.incoming_id is None and self.expected_incoming_version is not None:
            raise ValueError("expected_incoming_version requires incoming_id")
        return self


class ConnectorServiceOrderResult(BaseModel):
    order_id: int
    customer_id: int
    proposal_id: int
    status: str
    proposal_status: str
    workflow_type: str
    service_type: str | None
    incoming_id: int | None
    incoming_version: int | None
    manager_url: str
    proposal_manager_url: str
