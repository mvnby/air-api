"""Portable Manager order export and import contracts."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from models import PaymentCurrency
from schemas_manager_orders import OrderProductLogisticsComponent


class ManagerOrderTransferCustomer(BaseModel):
    source_id: Optional[int] = None
    type: str = "individual"
    name: str
    phone: str = ""
    email: Optional[str] = None
    full_legal_name: Optional[str] = None
    inn: Optional[str] = None
    legal_address: Optional[str] = None
    actual_address: Optional[str] = None
    bank_name: Optional[str] = None
    bic: Optional[str] = None
    iban: Optional[str] = None


class ManagerOrderTransferCustomerBranch(BaseModel):
    source_id: Optional[int] = None
    name: Optional[str] = None
    delivery_address: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    is_default: bool = False


class ManagerOrderTransferProductRef(BaseModel):
    source_id: Optional[int] = None
    title: str
    slug: Optional[str] = None
    source_url: Optional[str] = None


class ManagerOrderTransferServiceRef(BaseModel):
    source_id: Optional[int] = None
    title: str
    slug: Optional[str] = None


class ManagerOrderTransferProductLine(BaseModel):
    source_id: Optional[int] = None
    product: ManagerOrderTransferProductRef
    quantity: int
    price: int
    cost: int = 0
    is_installation_included: bool = False
    installation_price: int = 0
    installation_details: Optional[Dict[str, Any]] = None
    logistics_components: Optional[List[OrderProductLogisticsComponent]] = None


class ManagerOrderTransferServiceLine(BaseModel):
    source_id: Optional[int] = None
    service: Optional[ManagerOrderTransferServiceRef] = None
    title: str
    quantity: int
    price: int
    cost: int = 0


class ManagerOrderTransferProposal(BaseModel):
    source_id: Optional[int] = None
    name: str = "Основное"
    status: str = "draft"
    is_selected: bool = False
    is_archived: bool = False
    sort_order: int = 0
    product_lines: List[ManagerOrderTransferProductLine] = Field(default_factory=list)
    service_lines: List[ManagerOrderTransferServiceLine] = Field(default_factory=list)


class ManagerOrderTransferPayment(BaseModel):
    source_id: Optional[int] = None
    amount: float
    currency: PaymentCurrency = PaymentCurrency.BYN
    date: datetime
    type: str = "prepayment"
    comment: Optional[str] = None


class ManagerOrderTransferWorkStage(BaseModel):
    source_id: Optional[int] = None
    name: str
    status: str = "planned"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    installer_name: Optional[str] = None
    manager_comment: Optional[str] = None
    installer_report: Optional[str] = None


class ManagerOrderTransferOrder(BaseModel):
    source_id: Optional[int] = None
    status: str = "negotiation"
    lead_source: Optional[str] = "manager"
    title: Optional[str] = None
    workflow_type: str = "sales_installation"
    repair_meta: Dict[str, Any] = Field(default_factory=dict)
    manager_labels: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    next_followup_date: Optional[datetime] = None
    measurement_date: Optional[datetime] = None
    installation_date: Optional[datetime] = None
    comment: Optional[str] = None
    delivery_address: Optional[str] = None
    document_role_type: Optional[str] = None
    additional_conditions: Optional[str] = None
    closing_result: Optional[str] = None
    reject_reason: Optional[str] = None
    is_on_hold: bool = False
    on_hold_reason: Optional[str] = None
    measurement_required: bool = False
    measurement_result: Optional[str] = None
    proposal_status: str = "draft"
    proposal_sent_at: Optional[datetime] = None
    negotiation_status: str = "awaiting_offer"
    negotiation_status_changed_at: Optional[datetime] = None
    execution_without_payment: bool = False
    execution_without_payment_reason: Optional[str] = None
    auto_execution_on_payment: bool = False
    auto_close_on_payment: bool = False
    execution_status: str = "needs_schedule"
    execution_status_changed_at: Optional[datetime] = None
    equipment_status: str = "pending"
    standard_install_kit_issued: bool = False
    target_currency: Optional[PaymentCurrency] = None
    target_currency_amount: Optional[float] = None
    customer: Optional[ManagerOrderTransferCustomer] = None
    customer_branch: Optional[ManagerOrderTransferCustomerBranch] = None
    proposals: List[ManagerOrderTransferProposal] = Field(default_factory=list)
    payments: List[ManagerOrderTransferPayment] = Field(default_factory=list)
    work_stages: List[ManagerOrderTransferWorkStage] = Field(default_factory=list)


class ManagerOrderTransferPackage(BaseModel):
    version: int = 1
    exported_at: datetime
    source: str = "manager"
    orders: List[ManagerOrderTransferOrder] = Field(default_factory=list)


class ManagerOrderImportPreviewRequest(BaseModel):
    package: ManagerOrderTransferPackage


class ManagerOrderImportCommitRequest(BaseModel):
    package: ManagerOrderTransferPackage


class ManagerOrderImportProductMatch(BaseModel):
    source_order_id: Optional[int] = None
    product_title: str
    product_slug: Optional[str] = None
    matched_product_id: Optional[int] = None
    matched_product_title: Optional[str] = None
    status: str
    reason: Optional[str] = None


class ManagerOrderImportCustomerMatch(BaseModel):
    source_order_id: Optional[int] = None
    customer_name: Optional[str] = None
    matched_customer_id: Optional[int] = None
    matched_customer_name: Optional[str] = None
    status: str
    reason: Optional[str] = None


class ManagerOrderImportPreviewResponse(BaseModel):
    orders_count: int
    products_total: int
    products_matched: int
    products_missing: int
    customers: List[ManagerOrderImportCustomerMatch] = Field(default_factory=list)
    products: List[ManagerOrderImportProductMatch] = Field(default_factory=list)
    can_import: bool
    warnings: List[str] = Field(default_factory=list)


class ManagerOrderImportCommitResponse(BaseModel):
    created_order_ids: List[int] = Field(default_factory=list)
    created_count: int
    skipped_payments: int = 0
    warnings: List[str] = Field(default_factory=list)
