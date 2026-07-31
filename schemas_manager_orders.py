"""Manager order command and projection API contracts."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field, field_validator

from models import PaymentCurrency
from schemas_common import Meta
from schemas_manager_installers import ManagerInstallerResponse


class CalendarEventType(str, Enum):
    MEASUREMENT = "measurement"
    INSTALLATION = "installation"
    WORK_STAGE = "work_stage"


class CalendarEventResponse(BaseModel):
    id: str
    order_id: int
    type: CalendarEventType
    date: datetime
    status: str
    customer_name: Optional[str] = None
    address: Optional[str] = None
    title: str
    start: datetime
    allDay: bool = True
    color: str


class OrderCustomerBrief(BaseModel):
    id: int
    type: str
    name: str
    phone: str
    email: Optional[str] = None
    full_legal_name: Optional[str] = None
    inn: Optional[str] = None
    legal_address: Optional[str] = None
    bank_name: Optional[str] = None
    bic: Optional[str] = None
    iban: Optional[str] = None
    signer_position: Optional[str] = None
    signer_name: Optional[str] = None
    acting_basis: Optional[str] = None


class OrderCustomerBranchBrief(BaseModel):
    id: int
    name: Optional[str] = None
    delivery_address: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    is_default: bool = False


class OrderCustomerContractBrief(BaseModel):
    id: int
    customer_id: int
    number: str
    valid_from: datetime
    valid_until: datetime
    status: str
    document_role_type: Optional[str] = None
    edit_url: Optional[str] = None


LOGISTICS_COMPONENT_KINDS = {"indoor", "outdoor", "accessory", "other"}


class OrderProductLogisticsComponent(BaseModel):
    title: str
    country: Optional[str] = None
    unit: str = "шт."
    quantity_per_parent: int = 1
    unit_price: float = 0.0
    kind: Optional[str] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            raise ValueError("component title is required")
        return cleaned

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, value: Optional[str]) -> Optional[str]:
        cleaned = " ".join(str(value or "").split())
        return cleaned or None

    @field_validator("unit")
    @classmethod
    def normalize_unit(cls, value: str) -> str:
        return " ".join(str(value or "").split()) or "шт."

    @field_validator("quantity_per_parent")
    @classmethod
    def validate_quantity_per_parent(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity_per_parent must be greater than zero")
        return value

    @field_validator("unit_price")
    @classmethod
    def validate_unit_price(cls, value: float) -> float:
        if value < 0:
            raise ValueError("unit_price must be >= 0")
        return value

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: Optional[str]) -> Optional[str]:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            return None
        if cleaned not in LOGISTICS_COMPONENT_KINDS:
            raise ValueError("invalid logistics component kind")
        return cleaned


class ProductLogisticsComponentTemplate(BaseModel):
    title: str
    country: Optional[str] = None
    unit: str = "шт."
    quantity_per_parent: int = 1
    price_weight: float = 1.0
    kind: Optional[str] = None


class OrderProductLineResponse(BaseModel):
    id: int
    proposal_id: Optional[int] = None
    product_id: Optional[int] = None
    product_title: str
    quantity: int
    price: int
    cost: int
    is_installation_included: bool
    installation_price: int
    line_total: int
    product_country: Optional[str] = None
    product_logistics_components: List[ProductLogisticsComponentTemplate] = Field(
        default_factory=list
    )
    logistics_components: List[OrderProductLogisticsComponent] = Field(
        default_factory=list
    )


class OrderServiceLineResponse(BaseModel):
    id: int
    proposal_id: Optional[int] = None
    service_id: Optional[int] = None
    service_title: str
    service_category: Optional[str] = None
    quantity: int
    price: int
    cost: int
    line_total: int


class ManagerOrderListItemResponse(BaseModel):
    id: int
    status: str
    lead_source: Optional[str] = None
    title: Optional[str] = None
    workflow_type: str = "sales_installation"
    repair_meta: Dict[str, Any] = Field(default_factory=dict)
    manager_labels: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None
    status_changed_at: Optional[datetime] = None
    next_followup_date: Optional[datetime] = None
    measurement_date: Optional[datetime] = None
    installation_date: Optional[datetime] = None
    total_amount: float
    total_cost: float
    margin: float
    is_paid: bool
    comment: Optional[str] = None
    delivery_address: Optional[str] = None
    customer: Optional[OrderCustomerBrief] = None
    customer_branch: Optional[OrderCustomerBranchBrief] = None
    customer_contract_id: Optional[int] = None
    customer_contract: Optional[OrderCustomerContractBrief] = None
    document_role_type: Optional[str] = None
    effective_document_role_type: str = "seller_buyer"
    additional_conditions: Optional[str] = None
    installer_id: Optional[int] = None
    installer: Optional[ManagerInstallerResponse] = None
    equipment_status: str = "pending"
    standard_install_kit_issued: bool = False
    target_currency: Optional[PaymentCurrency] = None
    target_currency_amount: Optional[float] = None
    target_currency_payments: Optional[float] = None
    closing_result: Optional[str] = None
    reject_reason: Optional[str] = None
    is_on_hold: bool = False
    on_hold_reason: Optional[str] = None
    measurement_required: bool = False
    measurer_id: Optional[int] = None
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
    total_payments: float = 0.0
    balance_due: float = 0.0

    @computed_field
    @property
    def needs_attention(self) -> bool:
        if self.measurement_date and not self.measurement_result:
            return self.measurement_date.timestamp() < datetime.now().timestamp()
        return False

    @computed_field
    @property
    def awaiting_measurement(self) -> bool:
        if self.measurement_required and self.measurement_date:
            return self.measurement_date.timestamp() > datetime.now().timestamp()
        return False

    @computed_field
    @property
    def client_thinking(self) -> bool:
        return self.proposal_status == "sent"

    @computed_field
    @property
    def ready_for_execution(self) -> bool:
        return self.status == "execution" or self.proposal_status == "approved"


class ManagerOrderDocumentItem(BaseModel):
    id: int
    proposal_id: Optional[int] = None
    base_document_id: Optional[int] = None
    base_customer_contract_id: Optional[int] = None
    scope_customer_branch_id: Optional[int] = None
    scope_title: Optional[str] = None
    scope_address: Optional[str] = None
    scope_meta: Dict[str, Any] = Field(default_factory=dict)
    base_document_type: Optional[str] = None
    base_document_type_label: Optional[str] = None
    base_document_number: Optional[str] = None
    base_document_date: Optional[datetime] = None
    doc_type: str
    number: str
    date: datetime
    edit_url: Optional[str] = None
    is_downloadable: bool = True


class ManagerOrderDocumentListResponse(BaseModel):
    items: List[ManagerOrderDocumentItem]


class ManagerCustomerDocumentItem(BaseModel):
    id: int
    order_id: int
    proposal_id: Optional[int] = None
    base_document_id: Optional[int] = None
    base_customer_contract_id: Optional[int] = None
    scope_customer_branch_id: Optional[int] = None
    scope_title: Optional[str] = None
    scope_address: Optional[str] = None
    scope_meta: Dict[str, Any] = Field(default_factory=dict)
    base_document_type: Optional[str] = None
    base_document_type_label: Optional[str] = None
    base_document_number: Optional[str] = None
    base_document_date: Optional[datetime] = None
    doc_type: str
    number: str
    date: datetime
    edit_url: Optional[str] = None
    is_downloadable: bool = True


class ManagerCustomerDocumentListResponse(BaseModel):
    items: List[ManagerCustomerDocumentItem]


class ManagerCustomerReconciliationBasisDocument(BaseModel):
    id: int
    doc_type: str
    doc_type_label: str
    number: str
    date: datetime
    edit_url: Optional[str] = None


class ManagerCustomerReconciliationDocumentItem(BaseModel):
    order_id: int
    order_title: str
    date: datetime
    amount: float
    basis: str
    delivery_address: Optional[str] = None
    documents: List[ManagerCustomerReconciliationBasisDocument] = Field(
        default_factory=list
    )


class ManagerCustomerReconciliationPaymentItem(BaseModel):
    payment_id: int
    order_id: int
    order_title: str
    date: datetime
    amount: float
    allocated_amount: Optional[float] = None
    currency: PaymentCurrency
    payment_type: str
    comment: Optional[str] = None
    bank_receipt_id: Optional[int] = None
    payer_name: Optional[str] = None
    payer_unp: Optional[str] = None
    payer_account: Optional[str] = None
    our_account: Optional[str] = None
    payment_document_number: Optional[str] = None
    payment_document_raw: Optional[str] = None
    payment_purpose: Optional[str] = None


class ManagerCustomerReconciliationResponse(BaseModel):
    customer_id: int
    date_from: date
    date_to: date
    opening_balance: float = 0.0
    documents_total: float = 0.0
    payments_total: float = 0.0
    closing_balance: float = 0.0
    documents: List[ManagerCustomerReconciliationDocumentItem] = Field(
        default_factory=list
    )
    payments: List[ManagerCustomerReconciliationPaymentItem] = Field(
        default_factory=list
    )


class ManagerCustomerReconciliationDocumentResponse(BaseModel):
    file_id: str
    edit_url: str
    title: str


class PaymentCreatePayload(BaseModel):
    amount: float = Field(gt=0)
    currency: PaymentCurrency = PaymentCurrency.BYN
    type: str
    comment: Optional[str] = None


class PaymentBankReceiptResponse(BaseModel):
    id: int
    status: str
    received_at: Optional[datetime] = None
    amount: float
    currency: PaymentCurrency
    payer_name: Optional[str] = None
    payer_unp: Optional[str] = None
    payer_account: Optional[str] = None
    payment_document_raw: Optional[str] = None
    payment_document_number: Optional[str] = None
    payment_purpose: Optional[str] = None


class PaymentResponse(BaseModel):
    id: int
    amount: float
    currency: PaymentCurrency
    date: datetime
    type: str
    comment: Optional[str] = None
    created_at: datetime
    bank_receipt_id: Optional[int] = None
    bank_receipt: Optional[PaymentBankReceiptResponse] = None


class OrderWorkStageCreatePayload(BaseModel):
    name: str
    status: Optional[str] = "planned"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    installer_id: Optional[int] = None
    manager_comment: Optional[str] = None
    installer_report: Optional[str] = None


class OrderWorkStageUpdatePayload(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    installer_id: Optional[int] = None
    manager_comment: Optional[str] = None
    installer_report: Optional[str] = None


class OrderWorkStageResponse(BaseModel):
    id: int
    order_id: int
    name: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    installer_id: Optional[int] = None
    manager_comment: Optional[str] = None
    installer_report: Optional[str] = None
    installer: Optional[ManagerInstallerResponse] = None


class ManagerStaleWorkStageItem(BaseModel):
    id: int
    order_id: int
    order_status: str
    order_title: Optional[str] = None
    name: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    installer_id: Optional[int] = None
    installer_name: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    address: Optional[str] = None
    manager_comment: Optional[str] = None
    installer_report: Optional[str] = None


class ManagerStaleWorkStageListResponse(BaseModel):
    items: List[ManagerStaleWorkStageItem]
    total: int


class OrderProposalResponse(BaseModel):
    id: int
    order_id: int
    name: str
    status: str = "draft"
    is_selected: bool = False
    is_archived: bool = False
    sort_order: int = 0
    total_amount: float = 0.0
    total_cost: float = 0.0
    margin: float = 0.0
    product_lines: List[OrderProductLineResponse] = Field(default_factory=list)
    service_lines: List[OrderServiceLineResponse] = Field(default_factory=list)


class OrderProposalCreatePayload(BaseModel):
    name: Optional[str] = None
    duplicate_from_proposal_id: Optional[int] = None


class OrderProposalUpdatePayload(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    is_archived: Optional[bool] = None


class OrderProposalListResponse(BaseModel):
    items: List[OrderProposalResponse]


class ManagerOrderDetailResponse(ManagerOrderListItemResponse):
    attachment_count: int = 0
    linked_equipment_count: int = 0
    product_lines: List[OrderProductLineResponse] = Field(default_factory=list)
    service_lines: List[OrderServiceLineResponse] = Field(default_factory=list)
    proposals: List[OrderProposalResponse] = Field(default_factory=list)
    documents: List[ManagerOrderDocumentItem] = Field(default_factory=list)
    payments: List[PaymentResponse] = Field(default_factory=list)
    work_stages: List[OrderWorkStageResponse] = Field(default_factory=list)


class ManagerOrderListResponse(BaseModel):
    items: List[ManagerOrderListItemResponse]
    meta: Meta


class ManagerOrderProductLinePayload(BaseModel):
    link_id: Optional[int] = None
    proposal_id: Optional[int] = None
    product_id: int
    quantity: int
    price: int
    cost: Optional[int] = None
    logistics_components: Optional[List[OrderProductLogisticsComponent]] = None


class ManagerOrderServiceLinePayload(BaseModel):
    link_id: Optional[int] = None
    proposal_id: Optional[int] = None
    service_id: Optional[int] = None
    title: str
    quantity: int
    price: int
    cost: Optional[int] = None


class ManagerOrderUpdatePayload(BaseModel):
    status: Optional[str] = None
    title: Optional[str] = None
    workflow_type: Optional[str] = None
    repair_meta: Optional[Dict[str, Any]] = None
    manager_labels: Optional[List[str]] = None
    next_followup_date: Optional[datetime] = None
    measurement_date: Optional[datetime] = None
    installation_date: Optional[datetime] = None
    comment: Optional[str] = None
    no_answer_at: Optional[str] = None
    measurement_required: Optional[bool] = None
    measurer_id: Optional[int] = None
    measurement_result: Optional[str] = None
    additional_conditions: Optional[str] = None
    proposal_status: Optional[str] = None
    proposal_sent_at: Optional[datetime] = None
    negotiation_status: Optional[str] = None
    execution_without_payment: Optional[bool] = None
    execution_without_payment_reason: Optional[str] = None
    auto_execution_on_payment: Optional[bool] = None
    auto_close_on_payment: Optional[bool] = None
    execution_status: Optional[str] = None
    is_paid: Optional[bool] = None
    closing_result: Optional[str] = None
    reject_reason: Optional[str] = None
    is_on_hold: Optional[bool] = None
    on_hold_reason: Optional[str] = None
    target_currency: Optional[PaymentCurrency] = None
    target_currency_amount: Optional[float] = None
    equipment_status: Optional[str] = None
    standard_install_kit_issued: Optional[bool] = None
    customer_id: Optional[int] = None
    customer_branch_id: Optional[int] = None
    customer_contract_id: Optional[int] = None
    document_role_type: Optional[str] = None
    customer_type: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    customer_inn: Optional[str] = None
    customer_full_legal_name: Optional[str] = None
    customer_legal_address: Optional[str] = None
    customer_bank_name: Optional[str] = None
    customer_bic: Optional[str] = None
    customer_iban: Optional[str] = None
    customer_delivery_address: Optional[str] = None
    confirm_critical_customer_changes: Optional[bool] = None
    object_type: Optional[str] = None
    service_type: Optional[str] = None
    equipment_class: Optional[str] = None
    marketing_source: Optional[str] = None
    installer_id: Optional[int] = None
    products: Optional[List[ManagerOrderProductLinePayload]] = None
    services: Optional[List[ManagerOrderServiceLinePayload]] = None


class ManagerOrderCreatePayload(BaseModel):
    customer_id: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    source: str
    request_text: str
    service_type: Optional[str] = None
    customer_type: str = "individual"
    customer_inn: Optional[str] = None
    customer_full_legal_name: Optional[str] = None
    target_date: Optional[datetime] = None
    address: Optional[str] = None


class ManagerOrderExportRequest(BaseModel):
    order_ids: List[int] = Field(default_factory=list, min_length=1, max_length=100)
    include_payments: bool = True
    include_work_stages: bool = True


class ManagerOrderDocumentResponse(BaseModel):
    doc_id: int
    proposal_id: Optional[int] = None
    base_document_id: Optional[int] = None
    base_customer_contract_id: Optional[int] = None
    scope_customer_branch_id: Optional[int] = None
    scope_title: Optional[str] = None
    scope_address: Optional[str] = None
    scope_meta: Dict[str, Any] = Field(default_factory=dict)
    doc_type: str
    edit_url: str


class ManagerOrderDocumentGeneratePayload(BaseModel):
    additional_conditions: Optional[str] = None
