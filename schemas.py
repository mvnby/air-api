from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict, Field, field_validator, computed_field
from datetime import datetime
from enum import Enum
from core.input_validation import (
    validate_optional_bic,
    validate_optional_email,
    validate_optional_iban,
    validate_optional_phone,
    validate_optional_unp,
    validate_required_phone,
)
from models import EquipmentServiceEventType, PaymentCurrency

# --- SHARED ---

class FxRateResponse(BaseModel):
    usd_byn: Optional[float] = None
    eur_byn: Optional[float] = None
    source: str = "manual"


class AddressSuggestionItem(BaseModel):
    title: str
    subtitle: Optional[str] = None
    value: str


class AddressSuggestResponse(BaseModel):
    items: List[AddressSuggestionItem] = []

class Meta(BaseModel):
    total: int
    page: int
    limit: int
    pages: int

# --- CATALOG ---

class ProductBase(BaseModel):
    id: int
    title: str
    slug: Optional[str]
    price: int
    old_price: Optional[int]
    area: int
    is_inverter: bool
    power_cooling: Optional[float]
    main_image: Optional[str]
    card_image: Optional[str] = None
    full_image: Optional[str] = None
    is_published: bool
    created_at: datetime

class TagGroupResponse(BaseModel):
    title: str
    slug: str
    is_public: bool = True

class TagResponse(BaseModel):
    id: int
    title: str
    slug: str
    is_public: bool = True
    sort_order: int = 0
    group: Optional[TagGroupResponse] = None
    group_title: Optional[str] = None

class ProductImageResponse(BaseModel):
    id: int
    url: str
    is_installation_photo: bool
    card_variant_url: Optional[str] = None
    full_variant_url: Optional[str] = None


class ProductManualResponse(BaseModel):
    id: int
    kind: str = "manual"
    title: str
    url: str
    source: Optional[str] = None


class ProductManualPayload(BaseModel):
    kind: str = "manual"
    title: str
    url: str
    source: Optional[str] = None


class ProductSiblingResponse(BaseModel):
    id: int
    title: str
    slug: Optional[str]
    price: int
    old_price: Optional[int]
    area: int
    is_inverter: bool
    main_image: Optional[str]


class ProductResponse(ProductBase):
    vitebsk_qty: int = 0
    minsk_qty: int = 0
    availability_status: Optional[str] = None
    tags: List[TagResponse] = []
    specs: Dict[str, Any] = {}
    images: List[str] = [] # Legacy
    gallery_images: List[ProductImageResponse] = [] # New
    manuals: List[ProductManualResponse] = []
    series_siblings: List[ProductSiblingResponse] = []


class ProductListResponse(ProductBase):
    """Lightweight product payload for list/search views."""
    pass

class ProductPriceResponse(BaseModel):
    id: int
    price: int
    in_stock: bool = True

class CatalogResponse(BaseModel):
    items: List[ProductResponse]
    meta: Meta

class BulkSpecUpdate(BaseModel):
    product_ids: List[int]
    specs: Dict[str, Any]  # Словарь характеристик для добавления/обновления
    operation: str = "merge" # "merge" (добавить/обновить), "replace" (затереть всё старое), "delete_keys" (удалить эти ключи)

class BulkGalleryAddRequest(BaseModel):
    product_ids: List[int]
    source_urls: List[str]
    set_main: bool = False
    skip_existing: bool = True
    is_installation: bool = False

class BulkGalleryDeleteRequest(BaseModel):
    product_ids: List[int]
    urls: List[str]
    exclude_installation: bool = True

class CommonGalleryImageResponse(BaseModel):
    url: str
    product_count: int

class SpecsKeysResponse(BaseModel):
    keys: List[str]
    total_products_using: Dict[str, int] # Статистика: ключ -> кол-во товаров


class FilterRange(BaseModel):
    min: Optional[int] = None
    max: Optional[int] = None


class FilterTagOption(BaseModel):
    id: int
    title: str
    slug: str
    logo_url: Optional[str] = None
    sort_order: Optional[int] = None


class FiltersConfigResponse(BaseModel):
    price: FilterRange
    area: FilterRange
    brands: List[FilterTagOption] = []
    expert_tags: List[FilterTagOption] = []

# --- CONTENT ---

class ArticleResponse(BaseModel):
    id: int
    title: str
    slug: str
    content: str
    main_image: Optional[str]
    created_at: datetime

class ServiceResponse(BaseModel):
    id: int
    title: str
    slug: str
    category: str
    is_active: bool
    image: Optional[str]
    description: Optional[str]
    base_price: int

# --- ORDERS ---

class CalendarEventType(str, Enum):
    MEASUREMENT = "measurement"
    INSTALLATION = "installation"
    WORK_STAGE = "work_stage"

class CalendarEventResponse(BaseModel):
    id: str  # Unique ID for the event (e.g. "123-assessment")
    order_id: int
    type: CalendarEventType
    date: datetime
    status: str
    customer_name: Optional[str] = None
    address: Optional[str] = None

    # FullCalendar fields
    title: str
    start: datetime
    allDay: bool = True
    color: str


class CartItemPayload(BaseModel):
    product_id: Optional[int] = None
    quantity: int = 1
    # Installation snapshot fields (Phase: Snapshot Pricing Refactor)
    with_installation: bool = False
    installation_price: float = 0.0
    installation_meta: Optional[Dict] = None
    installation_options: Optional[List[str]] = []

class CustomerPayload(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None # For delivery
    type: str = "individual" # "individual" or "company"
    full_legal_name: Optional[str] = None
    inn: Optional[str] = None
    legal_address: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)

    @field_validator("iban")
    @classmethod
    def _validate_iban(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_iban(value)

    @field_validator("bic")
    @classmethod
    def _validate_bic(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_bic(value)

class OrderPayload(BaseModel):
    customer: CustomerPayload
    items: List[CartItemPayload] = []
    comment: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    status: str
    total_amount: float
    created_at: datetime


class ProductAvailabilityLeadPayload(BaseModel):
    product_id: int
    phone: str
    name: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)


class ProductAvailabilityLeadResponse(BaseModel):
    lead_id: int
    status: str
    created_at: datetime


# --- INSTALLERS ---

class ManagerInstallerBase(BaseModel):
    name: str
    is_active: bool = True
    default_rate: Optional[float] = None
    telegram_id: Optional[int] = None

class ManagerInstallerCreatePayload(ManagerInstallerBase):
    pass

class ManagerInstallerUpdatePayload(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    default_rate: Optional[float] = None
    telegram_id: Optional[int] = None

class ManagerInstallerResponse(ManagerInstallerBase):
    id: int

class ManagerInstallerListResponse(BaseModel):
    items: List[ManagerInstallerResponse]
    meta: Meta

# --- ORDERS ---

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
    product_logistics_components: List[ProductLogisticsComponentTemplate] = Field(default_factory=list)
    logistics_components: List[OrderProductLogisticsComponent] = Field(default_factory=list)


class OrderServiceLineResponse(BaseModel):
    id: int
    proposal_id: Optional[int] = None
    service_id: Optional[int] = None
    service_title: str
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
    # New fields
    equipment_status: str = "pending"
    standard_install_kit_issued: bool = False

    # Target Currency
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

    # Financials
    total_payments: float = 0.0
    balance_due: float = 0.0


class ManagerOrderDocumentItem(BaseModel):
    id: int
    proposal_id: Optional[int] = None
    base_document_id: Optional[int] = None
    base_customer_contract_id: Optional[int] = None
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


class PaymentCreatePayload(BaseModel):
    amount: float
    currency: PaymentCurrency = PaymentCurrency.BYN
    type: str # prepayment or postpayment
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
    product_lines: List[OrderProductLineResponse] = []
    service_lines: List[OrderServiceLineResponse] = []
    proposals: List[OrderProposalResponse] = []
    documents: List[ManagerOrderDocumentItem] = []
    payments: List[PaymentResponse] = []
    work_stages: List[OrderWorkStageResponse] = []


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

    # Negotiation
    measurement_required: Optional[bool] = None
    measurer_id: Optional[int] = None
    measurement_result: Optional[str] = None
    additional_conditions: Optional[str] = None
    proposal_status: Optional[str] = None
    proposal_sent_at: Optional[datetime] = None

    is_paid: Optional[bool] = None
    # Closing
    closing_result: Optional[str] = None
    reject_reason: Optional[str] = None
    # On Hold
    is_on_hold: Optional[bool] = None
    on_hold_reason: Optional[str] = None

    # Target Currency
    target_currency: Optional[PaymentCurrency] = None
    target_currency_amount: Optional[float] = None

    # Equipment
    equipment_status: Optional[str] = None
    standard_install_kit_issued: Optional[bool] = None

    # Customer Details
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

    # Qualification Meta fields
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


class ManagerOrderDocumentResponse(BaseModel):
    doc_id: int
    proposal_id: Optional[int] = None
    base_document_id: Optional[int] = None
    base_customer_contract_id: Optional[int] = None
    doc_type: str
    edit_url: str


class DocumentTemplateItem(BaseModel):
    id: str
    document_template_id: Optional[int] = None
    name: str
    document_role_type: str = "seller_buyer"
    is_open_contract: bool = False
    doc_type: str = "contract"
    description: Optional[str] = None
    base_document_type_label: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    client_restricted: bool = False
    sort_order: int = 0
    customer_ids: List[int] = Field(default_factory=list)
    linked_contract_template_ids: List[int] = Field(default_factory=list)
    linked_act_template_ids: List[int] = Field(default_factory=list)


class DocumentTemplateListResponse(BaseModel):
    items: List[DocumentTemplateItem]


class DocumentTemplateFileItem(BaseModel):
    id: str
    name: str
    mime_type: Optional[str] = None
    created_time: Optional[str] = None


class DocumentTemplateFileListResponse(BaseModel):
    items: List[DocumentTemplateFileItem]


class DocumentTemplatePayload(BaseModel):
    name: str
    doc_type: str
    google_template_id: str
    document_role_type: Optional[str] = None
    description: Optional[str] = None
    base_document_type_label: Optional[str] = None
    is_default: bool = False
    is_active: bool = True
    is_open_contract: bool = False
    client_restricted: bool = False
    sort_order: int = 0
    customer_ids: List[int] = Field(default_factory=list)
    linked_contract_template_ids: List[int] = Field(default_factory=list)
    linked_act_template_ids: List[int] = Field(default_factory=list)


class DocumentTemplateUpdatePayload(BaseModel):
    name: Optional[str] = None
    doc_type: Optional[str] = None
    google_template_id: Optional[str] = None
    document_role_type: Optional[str] = None
    description: Optional[str] = None
    base_document_type_label: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    is_open_contract: Optional[bool] = None
    client_restricted: Optional[bool] = None
    sort_order: Optional[int] = None
    customer_ids: Optional[List[int]] = None
    linked_contract_template_ids: Optional[List[int]] = None
    linked_act_template_ids: Optional[List[int]] = None




class LeadResponse(BaseModel):
    id: int
    status: str
    source: str
    segment_hint: str
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    company_name: Optional[str] = None
    request_text: str
    source_message_id: Optional[str] = None
    source_fingerprint: Optional[str] = None
    loss_reason: Optional[str] = None
    next_followup_date: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    converted_order_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class LeadListResponse(BaseModel):
    items: List[LeadResponse]
    meta: Meta


class LeadCreatePayload(BaseModel):
    source: str = "manager"
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    company_name: Optional[str] = None
    segment_hint: Optional[str] = None
    request_text: str
    source_message_id: Optional[str] = None
    source_fingerprint: Optional[str] = None
    next_followup_date: Optional[datetime] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)


class LeadUpdatePayload(BaseModel):
    status: Optional[str] = None
    source: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    company_name: Optional[str] = None
    segment_hint: Optional[str] = None
    request_text: Optional[str] = None
    source_message_id: Optional[str] = None
    source_fingerprint: Optional[str] = None
    loss_reason: Optional[str] = None
    next_followup_date: Optional[datetime] = None
    archived_at: Optional[datetime] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)


class LeadQualifyPayload(BaseModel):
    customer_id: Optional[int] = None
    customer_branch_id: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    full_legal_name: Optional[str] = None
    legal_address: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    delivery_address: Optional[str] = None
    customer_type: Optional[str] = None
    order_comment: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)

    @field_validator("iban")
    @classmethod
    def _validate_iban(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_iban(value)

    @field_validator("bic")
    @classmethod
    def _validate_bic(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_bic(value)


class LeadLossPayload(BaseModel):
    status: str = "lost"
    loss_reason: Optional[str] = None


class LeadQualifyResponse(BaseModel):
    lead: LeadResponse
    customer_id: int
    order_id: int


class ManagerAuthStatusResponse(BaseModel):
    username: str
    status: str


class ManagerCatalogProductImageResponse(BaseModel):
    id: int
    url: str
    is_installation_photo: bool


class ManagerCatalogProductManualResponse(BaseModel):
    id: int
    kind: str = "manual"
    title: str
    url: str
    source: Optional[str] = None


class ManagerCatalogProductTagResponse(BaseModel):
    id: int
    title: str
    slug: str
    group_title: Optional[str]
    group_color: Optional[str]


class ManagerCatalogProductItemResponse(BaseModel):
    id: int
    brand_id: Optional[int] = None
    series_id: Optional[int] = None
    title: str
    slug: Optional[str]
    price: int
    old_price: Optional[int]
    area: int
    is_inverter: bool
    power_cooling: Optional[float]
    main_image: Optional[str]
    is_published: bool
    created_at: datetime
    specs: Dict[str, Any]
    gallery_images: List[ManagerCatalogProductImageResponse]
    manuals: List[ManagerCatalogProductManualResponse]
    tags: List[ManagerCatalogProductTagResponse]
    min_cost_byn: Optional[float] = None
    recommended_price_byn: Optional[float] = None
    margin_abs_preview: Optional[float] = None
    margin_pct_preview: Optional[float] = None
    vitebsk_qty: int = 0
    minsk_qty: int = 0
    availability_status: str = "out_of_stock"


class ManagerCatalogProductListResponse(BaseModel):
    items: List[ManagerCatalogProductItemResponse]
    meta: Meta


class ManagerCatalogCustomerItemResponse(BaseModel):
    id: int
    name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    type: str
    inn: Optional[str]
    kpp: Optional[str] = None
    full_legal_name: Optional[str]
    legal_address: Optional[str]
    actual_address: Optional[str] = None
    iban: Optional[str]
    bic: Optional[str]
    bank_name: Optional[str]
    signer_position: Optional[str] = None
    signer_name: Optional[str] = None
    acting_basis: Optional[str] = None
    last_delivery_address: Optional[str] = None
    created_at: Optional[datetime]
    order_count: int
    is_favorite: bool = False
    branches: List["ManagerCustomerBranchItemResponse"] = Field(default_factory=list)


class ManagerCustomerBranchItemResponse(BaseModel):
    id: int
    customer_id: int
    name: Optional[str] = None
    delivery_address: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ManagerCustomerBranchListResponse(BaseModel):
    items: List[ManagerCustomerBranchItemResponse]


class ManagerEquipmentServiceHistoryItemResponse(BaseModel):
    id: int
    equipment_id: int
    order_id: Optional[int] = None
    event_type: EquipmentServiceEventType = EquipmentServiceEventType.OTHER
    event_date: datetime
    complaint_snapshot: Optional[str] = None
    diagnostic_result: Optional[str] = None
    repair_recommendation: Optional[str] = None
    refrigerant_type: Optional[str] = None
    refrigerant_amount: Optional[str] = None
    not_repairable: bool = False
    not_repairable_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ManagerEquipmentItemResponse(BaseModel):
    id: int
    customer_id: int
    customer_branch_id: Optional[int] = None
    equipment_type: str = "hvac"
    display_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = None
    notes: Optional[str] = None
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class ManagerEquipmentDetailResponse(ManagerEquipmentItemResponse):
    recent_history: List[ManagerEquipmentServiceHistoryItemResponse] = Field(default_factory=list)


class ManagerEquipmentListResponse(BaseModel):
    items: List[ManagerEquipmentItemResponse]
    meta: Meta


class ManagerEquipmentServiceHistoryListResponse(BaseModel):
    items: List[ManagerEquipmentServiceHistoryItemResponse]
    meta: Meta


class ManagerEquipmentCreatePayload(BaseModel):
    customer_id: int
    customer_branch_id: Optional[int] = None
    equipment_type: Optional[str] = "hvac"
    display_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = None
    notes: Optional[str] = None
    is_archived: bool = False

    @field_validator(
        "equipment_type",
        "display_name",
        "brand",
        "model",
        "serial",
        "inventory_number",
        "location_hint",
        "refrigerant_type",
        "notes",
    )
    @classmethod
    def _trim_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ManagerEquipmentUpdatePayload(BaseModel):
    customer_branch_id: Optional[int] = None
    equipment_type: Optional[str] = None
    display_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None

    @field_validator(
        "equipment_type",
        "display_name",
        "brand",
        "model",
        "serial",
        "inventory_number",
        "location_hint",
        "refrigerant_type",
        "notes",
    )
    @classmethod
    def _trim_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ManagerEquipmentServiceHistoryCreatePayload(BaseModel):
    event_type: EquipmentServiceEventType = EquipmentServiceEventType.OTHER
    event_date: Optional[datetime] = None
    order_id: Optional[int] = None
    complaint_snapshot: Optional[str] = None
    diagnostic_result: Optional[str] = None
    repair_recommendation: Optional[str] = None
    refrigerant_type: Optional[str] = None
    refrigerant_amount: Optional[str] = None
    not_repairable: bool = False
    not_repairable_reason: Optional[str] = None
    notes: Optional[str] = None

    @field_validator(
        "complaint_snapshot",
        "diagnostic_result",
        "repair_recommendation",
        "refrigerant_type",
        "refrigerant_amount",
        "not_repairable_reason",
        "notes",
    )
    @classmethod
    def _trim_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ManagerEquipmentHistoryFromRepairOrderPayload(BaseModel):
    order_id: int
    event_type: Optional[EquipmentServiceEventType] = None
    event_date: Optional[datetime] = None
    notes: Optional[str] = None

    @field_validator("notes")
    @classmethod
    def _trim_notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ManagerCustomerContractItemResponse(BaseModel):
    id: int
    customer_id: int
    number: str
    valid_from: datetime
    valid_until: datetime
    status: str
    template_id: Optional[str] = None
    document_role_type: str = "seller_buyer"
    edit_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ManagerCustomerContractListResponse(BaseModel):
    items: List[ManagerCustomerContractItemResponse]


class ManagerCustomerContractCreatePayload(BaseModel):
    number: Optional[str] = None
    template_id: Optional[str] = None
    document_role_type: Optional[str] = None
    contract_date: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class ManagerCustomerContractUpdatePayload(BaseModel):
    number: Optional[str] = None
    template_id: Optional[str] = None
    document_role_type: Optional[str] = None
    contract_date: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    status: Optional[str] = None


class ManagerCustomerBranchCreatePayload(BaseModel):
    name: Optional[str] = None
    delivery_address: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    is_default: bool = False

    @field_validator("name", "delivery_address", "contact_name")
    @classmethod
    def _trim_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("delivery_address")
    @classmethod
    def _validate_delivery_address(cls, value: Optional[str]) -> str:
        if not value:
            raise ValueError("Адрес филиала обязателен")
        return value

    @field_validator("contact_phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)


class ManagerCustomerBranchUpdatePayload(BaseModel):
    name: Optional[str] = None
    delivery_address: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    is_default: Optional[bool] = None

    @field_validator("name", "delivery_address", "contact_name")
    @classmethod
    def _trim_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("contact_phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)


class ManagerCatalogCustomerListResponse(BaseModel):
    items: List[ManagerCatalogCustomerItemResponse]
    meta: Meta


class ManagerCustomerUpdatePayload(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    type: Optional[str] = None
    inn: Optional[str] = None
    kpp: Optional[str] = None
    full_legal_name: Optional[str] = None
    legal_address: Optional[str] = None
    actual_address: Optional[str] = None
    bank_name: Optional[str] = None
    bic: Optional[str] = None
    iban: Optional[str] = None
    signer_position: Optional[str] = None
    signer_name: Optional[str] = None
    acting_basis: Optional[str] = None
    is_favorite: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Имя клиента не может быть пустым")
        return trimmed

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"individual", "company"}:
            raise ValueError("Тип клиента должен быть individual или company")
        return normalized

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)

    @field_validator("iban")
    @classmethod
    def _validate_iban(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_iban(value)

    @field_validator("bic")
    @classmethod
    def _validate_bic(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_bic(value)


class ManagerTagGroupCreatePayload(BaseModel):
    title: str
    slug: Optional[str] = None
    is_public: bool = True
    color: str = "secondary"
    allow_multiple: bool = False

class ManagerTagGroupUpdatePayload(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    is_public: Optional[bool] = None
    color: Optional[str] = None
    allow_multiple: Optional[bool] = None
    sort_order: Optional[int] = None

class ManagerTagCreatePayload(BaseModel):
    group_id: int
    title: str
    slug: Optional[str] = None
    is_public: bool = True
    is_filter: bool = False

class ManagerTagUpdatePayload(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    is_public: Optional[bool] = None
    is_filter: Optional[bool] = None
    sort_order: Optional[int] = None

class ManagerTagOptionResponse(BaseModel):
    id: int
    title: str
    slug: str
    is_public: bool
    is_filter: bool


class ManagerTagGroupResponse(BaseModel):
    id: int
    title: str
    slug: str
    color: str
    is_public: bool
    allow_multiple: bool
    tags: List[ManagerTagOptionResponse]


class ManagerBrandResponse(BaseModel):
    id: int
    title: str
    slug: str
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_published: bool
    sort_order: int
    created_at: datetime
    products_count: int = 0


class ManagerBrandListResponse(BaseModel):
    items: List[ManagerBrandResponse]


class ManagerBrandCreatePayload(BaseModel):
    title: str
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_published: bool = True
    sort_order: int = 0


class ManagerBrandUpdatePayload(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    is_published: Optional[bool] = None
    sort_order: Optional[int] = None


class ManagerActionMessageResponse(BaseModel):
    message: str


class ManagerCrmHealthReportResponse(BaseModel):
    window_hours: int
    events_total: int
    errors_total: int
    invalid_payload_errors: int
    requisite_conflict_attempts: int
    qualify_success_total: int
    qualify_success_without_manual_overwrite: int
    qualify_success_without_manual_overwrite_pct: float


class ManagerBulkRoundPriceResponse(ManagerActionMessageResponse):
    updated_count: int


class ManagerBulkSetRrcPriceResponse(ManagerActionMessageResponse):
    processed_count: int
    updated_count: int
    skipped_count: int


class ManagerBulkDeleteProductsError(BaseModel):
    product_id: int
    message: str


class ManagerBulkDeleteProductsResponse(ManagerActionMessageResponse):
    deleted_count: int
    failed_count: int
    errors: List[ManagerBulkDeleteProductsError] = Field(default_factory=list)


class ManagerBulkSpecsResponse(ManagerActionMessageResponse):
    operation: str


class ManagerNormalizeLegacySpecsResponse(ManagerActionMessageResponse):
    dry_run: bool
    products_processed: int
    products_updated: int
    sample_changes: List[Dict[str, Any]]


class ManagerMediaImageSearchResultResponse(BaseModel):
    image: str
    width: Optional[int] = None
    height: Optional[int] = None
    thumbnail: Optional[str] = None


class ManagerMediaReuseSearchItemResponse(BaseModel):
    id: int
    title: str
    main_image: Optional[str] = None


class ManagerMediaImageLinkResponse(BaseModel):
    id: int
    url: str


class ProductImageVariantResponse(BaseModel):
    id: Optional[int] = None
    product_image_id: int
    variant_type: str
    url: Optional[str] = None
    storage_provider: str = "local"
    processing_status: str
    processing_stage: str
    processing_provider: Optional[str] = None
    manual_quality_status: str = "unreviewed"
    content_hash: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    processing_error: Optional[str] = None
    processed_at: Optional[datetime] = None


class ProductImageVariantCandidateResponse(BaseModel):
    product_image_id: int
    product_id: int
    url: str
    is_installation_photo: bool
    reason: str


class ProductImageVariantCandidatesResponse(BaseModel):
    dry_run: bool = True
    variant_type: str
    total_candidates: int
    returned: int
    candidates: List[ProductImageVariantCandidateResponse] = []


class ProductImageVariantBatchProcessResponse(BaseModel):
    dry_run: bool
    variant_type: str
    total_candidates: int = 0
    returned: int = 0
    candidates: List[ProductImageVariantCandidateResponse] = []
    processed: int = 0
    errors: List[Dict[str, Any]] = []
    variants: List[ProductImageVariantResponse] = []


class ManagerMediaSetMainImageResponse(ManagerActionMessageResponse):
    url: str


class ManagerMediaDeleteImageResponse(ManagerActionMessageResponse):
    pass


class ManagerMediaReuseImageResponse(ManagerActionMessageResponse):
    id: int


class ManagerMediaBulkAddResponse(ManagerActionMessageResponse):
    products_count: int
    added_links: int
    skipped_existing: int


class ManagerMediaBulkDeleteResponse(ManagerActionMessageResponse):
    products_count: int
    deleted_links: int


class ManagerMediaBulkUploadResponse(ManagerActionMessageResponse):
    products_count: int
    files_count: int
    uploaded_links: int


class ManagerMediaUploadLocalImagesResponse(BaseModel):
    uploaded: int
    images: List[ManagerMediaImageLinkResponse]


class ManagerMediaCleanupResponse(BaseModel):
    dry_run: bool
    deleted_count: int
    reclaimed_bytes: int
    files: List[str]


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    price: Optional[int] = None
    old_price: Optional[int] = None
    slug: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    is_published: Optional[bool] = None
    brand_id: Optional[int] = None
    series_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    manuals: List[ProductManualPayload] = Field(default_factory=list)


class SupplierResponse(BaseModel):
    id: int
    name: str
    code: str
    is_active: bool
    priority: int
    spreadsheet_id: Optional[str] = None
    spreadsheet_url: Optional[str] = None
    google_sheet_synced_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class SupplierCreatePayload(BaseModel):
    name: str
    code: Optional[str] = None
    spreadsheet_id_or_url: Optional[str] = None
    is_active: bool = True
    priority: int = 100


class SupplierUpdatePayload(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    spreadsheet_id_or_url: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None


class SupplierListResponse(BaseModel):
    items: List[SupplierResponse]


class SupplierPriceSourceResponse(BaseModel):
    id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    source_type: str
    sheet_name: Optional[str] = None
    range_a1: Optional[str] = None
    city_bucket: str
    header_row_index: int
    col_external_id: str
    col_title: str
    col_wholesale: str
    col_wholesale_currency: str
    col_rrc_byn: str
    col_qty: str
    is_active: bool
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SupplierPriceSourceCreatePayload(BaseModel):
    supplier_id: int
    source_type: str = "google_sheet"
    sheet_name: Optional[str] = None
    range_a1: Optional[str] = None
    city_bucket: str = "minsk"
    header_row_index: int = 1
    col_external_id: str = "A"
    col_title: str = "B"
    col_wholesale: str = "C"
    col_wholesale_currency: str = "D"
    col_rrc_byn: str = "E"
    col_qty: str = "F"
    is_active: bool = True


class SupplierPriceSourceUpdatePayload(BaseModel):
    source_type: Optional[str] = None
    supplier_id: Optional[int] = None
    sheet_name: Optional[str] = None
    range_a1: Optional[str] = None
    city_bucket: Optional[str] = None
    header_row_index: Optional[int] = None
    col_external_id: Optional[str] = None
    col_title: Optional[str] = None
    col_wholesale: Optional[str] = None
    col_wholesale_currency: Optional[str] = None
    col_rrc_byn: Optional[str] = None
    col_qty: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierPriceSourceListResponse(BaseModel):
    items: List[SupplierPriceSourceResponse]


class SupplierSyncRunResponse(BaseModel):
    run_id: int
    source_id: int
    status: str
    rows_total: int
    rows_upserted: int
    rows_skipped: int
    rows_deactivated: int
    error: Optional[str] = None


class SupplierOfferResponse(BaseModel):
    supplier_id: int
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    supplier_name: Optional[str] = None
    external_id: str
    title_raw: Optional[str] = None
    qty: int
    qty_raw: Optional[str] = None
    wholesale_raw: Optional[str] = None
    wholesale_value: Optional[float] = None
    wholesale_currency: Optional[str] = None
    rrc_raw: Optional[str] = None
    rrc_byn: Optional[float] = None
    is_active: bool
    mapping_id: Optional[int] = None
    product_id: Optional[int] = None
    product_title: Optional[str] = None
    updated_at: datetime


class SupplierOfferListResponse(BaseModel):
    items: List[SupplierOfferResponse]
    meta: Meta


class SupplierMappingCreatePayload(BaseModel):
    product_id: int
    supplier_id: int
    external_id: str


class SupplierMappingBulkItemPayload(BaseModel):
    product_id: int
    supplier_id: int
    external_id: str


class SupplierMappingBulkCreatePayload(BaseModel):
    items: List[SupplierMappingBulkItemPayload]
    skip_conflicts: bool = True


class SupplierMappingBulkErrorResponse(BaseModel):
    supplier_id: Optional[int] = None
    external_id: Optional[str] = None
    message: str


class SupplierMappingBulkCreateResponse(BaseModel):
    created_count: int
    skipped_count: int
    errors: List[SupplierMappingBulkErrorResponse] = []


class SupplierOfferSuggestionRequestItem(BaseModel):
    supplier_id: int
    external_id: str
    title_raw: Optional[str] = None


class SupplierOfferSuggestionCandidate(BaseModel):
    product_id: int
    title: str
    price: int


class SupplierOfferSuggestionItem(BaseModel):
    supplier_id: int
    external_id: str
    normalized_query: str
    candidates: List[SupplierOfferSuggestionCandidate]
    auto_eligible: bool
    reason: str


class SupplierOfferSuggestionsPayload(BaseModel):
    items: List[SupplierOfferSuggestionRequestItem]
    limit_per_offer: int = 5


class SupplierOfferSuggestionsResponse(BaseModel):
    items: List[SupplierOfferSuggestionItem]


class SupplierSheetTabResponse(BaseModel):
    title: str
    index: Optional[int] = None
    sheet_id: Optional[int] = None


class SupplierSheetTabListResponse(BaseModel):
    items: List[SupplierSheetTabResponse]


class SupplierMappingResponse(BaseModel):
    id: int
    product_id: int
    supplier_id: int
    external_id: str
    is_active: bool
    mapped_by: Optional[str] = None
    mapped_at: datetime


class ProductLocalStockPayload(BaseModel):
    qty: int = 0


class ProductLocalStockResponse(BaseModel):
    id: int
    product_id: int
    warehouse_code: str
    qty: int
    updated_by: Optional[str] = None
    updated_at: datetime


class BulkRoundRequest(BaseModel):
    product_ids: List[int]


class BulkProductIdsRequest(BaseModel):
    product_ids: List[int]

# --- DASHBOARD STATS ---

class DashboardTouchpoint(BaseModel):
    order_id: int
    customer_name: str
    phone: Optional[str] = None
    next_followup_date: datetime
    title: Optional[str] = None


class DashboardContractExpiry(BaseModel):
    contract_id: int
    customer_id: int
    customer_name: str
    number: str
    valid_until: datetime
    edit_url: Optional[str] = None


class DashboardBankReceiptReviewItem(BaseModel):
    id: int
    received_at: Optional[datetime] = None
    amount: float
    currency: PaymentCurrency
    payer_name: Optional[str] = None
    payer_unp: Optional[str] = None
    payment_document_number: Optional[str] = None
    payment_purpose: Optional[str] = None
    candidate_order_ids: List[int] = []


class DashboardStatsResponse(BaseModel):
    total_amount: float
    new_leads_count: int
    upcoming_touchpoints: List[DashboardTouchpoint]
    expiring_contracts: List[DashboardContractExpiry] = []
    bank_receipts_review_count: int = 0
    bank_receipts_review: List[DashboardBankReceiptReviewItem] = []


# --- LEADS INBOX ---

class LeadsCounterResponse(BaseModel):
    count: int
    has_new: bool


class LeadsInboxItemResponse(BaseModel):
    id: int
    status: str
    is_new: bool
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = None
    comment: Optional[str] = None
    no_answer_at: Optional[datetime] = None
    source_created_at: Optional[datetime] = None
    created_at: datetime
    customer_type: Optional[str] = None
    customer_inn: Optional[str] = None
    customer_full_legal_name: Optional[str] = None
    customer_delivery_address: Optional[str] = None
    object_type: Optional[str] = None
    service_type: Optional[str] = None
    equipment_class: Optional[str] = None
    marketing_source: Optional[str] = None


class LeadsInboxListResponse(BaseModel):
    items: List[LeadsInboxItemResponse]
    total: int


# --- CATALOG IMPORT (universal) ---

class CatalogImportPayload(BaseModel):
    """Universal import payload — accepts URLs from any supported source
    (onliner.by, aircond.by, etc.).  ImporterService routes by domain."""
    urls: List[str]
    with_related: bool = False
    update_existing: bool = False


class CatalogImportResultResponse(BaseModel):
    success_count: int
    error_count: int
    successes: List[str]
    errors: List[str]


class CatalogImportJobStartResponse(BaseModel):
    job_id: str
    status: str
    stage: str


class CatalogImportJobStatusResponse(BaseModel):
    job_id: str
    status: str
    stage: str
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    input_total: int = 0
    total: int = 0
    processed: int = 0
    pending: int = 0
    success_count: int = 0
    error_count: int = 0
    current_url: Optional[str] = None
    current_title: Optional[str] = None
    successes: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)


# Backward-compatible aliases for the legacy import-onliner endpoint
OnlinerImportPayload = CatalogImportPayload
OnlinerImportResultResponse = CatalogImportResultResponse


# --- BACKUPS (Manager DR) ---

class ManagerBackupItemResponse(BaseModel):
    id: str
    name: str
    kind: str
    created_at: datetime
    size_bytes: Optional[int] = None
    mime_type: Optional[str] = None


class ManagerBackupListResponse(BaseModel):
    items: List[ManagerBackupItemResponse]


class ManagerRestoreJobStartResponse(BaseModel):
    job_id: str
    status: str
    stage: str


class ManagerRestoreJobStatusResponse(BaseModel):
    job_id: str
    file_id: str
    file_name: str
    kind: str
    status: str
    stage: str
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    safety_dump_path: Optional[str] = None


class ManagerBackupRunStartResponse(BaseModel):
    job_id: str
    status: str
    stage: str


class ManagerBackupRunStatusResponse(BaseModel):
    job_id: str
    status: str
    stage: str
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# --- SETTINGS ---

class ManagerGoogleAuthStatusResponse(BaseModel):
    exists: bool
    valid: bool
    expired: bool
    expiry: Optional[str] = None
    scopes: List[str] = []


class ManagerGoogleAuthUrlResponse(BaseModel):
    url: str

class ManagerSettingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    key: str
    value: str
    description: Optional[str] = None
    updated_at: datetime


class ManagerSettingUpdatePayload(BaseModel):
    value: str
    description: Optional[str] = None


class ManagerSettingCreatePayload(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


class ManagerSettingListResponse(BaseModel):
    items: List[ManagerSettingResponse]


# --- TARIFFS ---

class ManagerTariffServiceKind(str, Enum):
    installation = "installation"
    dismantling = "dismantling"
    maintenance = "maintenance"
    repair = "repair"


class ManagerTariffRuleType(str, Enum):
    fixed_once = "fixed_once"
    per_unit_manual = "per_unit_manual"
    per_meter_over_included = "per_meter_over_included"
    per_hole_manual = "per_hole_manual"


class ManagerTariffRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tariff_id: int
    rule_type: ManagerTariffRuleType
    name: str
    line_template: str
    unit: str
    unit_price: float
    is_optional: bool
    is_favorite: bool = False
    is_active: bool
    sort_order: int
    service_id: Optional[int] = None


class ManagerTariffRuleCreatePayload(BaseModel):
    rule_type: ManagerTariffRuleType
    name: str
    line_template: str = "{name}"
    unit: str = "шт"
    unit_price: float = 0.0
    is_optional: bool = False
    is_favorite: bool = False
    is_active: bool = True
    sort_order: int = 0
    service_id: Optional[int] = None

    @field_validator("unit_price")
    @classmethod
    def validate_unit_price(cls, value: float) -> float:
        if value < 0:
            raise ValueError("unit_price must be >= 0")
        return value


class ManagerTariffRuleUpdatePayload(BaseModel):
    rule_type: Optional[ManagerTariffRuleType] = None
    name: Optional[str] = None
    line_template: Optional[str] = None
    unit: Optional[str] = None
    unit_price: Optional[float] = None
    is_optional: Optional[bool] = None
    is_favorite: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    service_id: Optional[int] = None

    @field_validator("unit_price")
    @classmethod
    def validate_optional_unit_price(cls, value: Optional[float]) -> Optional[float]:
        if value is not None and value < 0:
            raise ValueError("unit_price must be >= 0")
        return value


class ManagerTariffRuleListResponse(BaseModel):
    items: List[ManagerTariffRuleResponse]


class ManagerTariffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    service_kind: ManagerTariffServiceKind
    selector_label: str
    estimate_template: str
    category: str
    power_range: str
    base_price: int
    included_route_meters: float
    is_active: bool
    sort_order: int
    comment: Optional[str] = None
    rules: List[ManagerTariffRuleResponse] = Field(default_factory=list)


class ManagerTariffCreatePayload(BaseModel):
    service_kind: ManagerTariffServiceKind = ManagerTariffServiceKind.installation
    selector_label: str
    estimate_template: str = "Монтаж кондиционера, включая расходные материалы"
    category: str = ""
    power_range: str = ""
    base_price: int = 0
    included_route_meters: float = 3.0
    is_active: bool = True
    sort_order: int = 0
    comment: Optional[str] = None


class ManagerTariffUpdatePayload(BaseModel):
    service_kind: Optional[ManagerTariffServiceKind] = None
    selector_label: Optional[str] = None
    estimate_template: Optional[str] = None
    category: Optional[str] = None
    power_range: Optional[str] = None
    base_price: Optional[int] = None
    included_route_meters: Optional[float] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    comment: Optional[str] = None


class ManagerTariffListResponse(BaseModel):
    items: List[ManagerTariffResponse]


class ManagerQuickTariffResponse(BaseModel):
    tariff_id: int
    service_kind: ManagerTariffServiceKind
    title: str
    price: int
    category: str = ""
    power_range: str = ""
    included_route_meters: float = 0.0


class ManagerQuickTariffListResponse(BaseModel):
    items: List[ManagerQuickTariffResponse]


# --- REPAIR COMPLAINT PRESETS ---

class ManagerRepairComplaintPresetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    complaint_group: str = ""
    customer_phrase: str
    document_wording: str = ""
    likely_diagnosis: str = ""
    is_favorite: bool = False
    is_active: bool = True
    sort_order: int = 0
    comment: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ManagerRepairComplaintPresetCreatePayload(BaseModel):
    complaint_group: str = ""
    customer_phrase: str
    document_wording: str = ""
    likely_diagnosis: str = ""
    is_favorite: bool = False
    is_active: bool = True
    sort_order: int = 0
    comment: Optional[str] = None


class ManagerRepairComplaintPresetUpdatePayload(BaseModel):
    complaint_group: Optional[str] = None
    customer_phrase: Optional[str] = None
    document_wording: Optional[str] = None
    likely_diagnosis: Optional[str] = None
    is_favorite: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    comment: Optional[str] = None


class ManagerRepairComplaintPresetListResponse(BaseModel):
    items: List[ManagerRepairComplaintPresetResponse]


class ManagerRepairActAiDraftPayload(BaseModel):
    defect_type: str
    defect_label: Optional[str] = None
    allow_assumptions: bool = False
    polish_existing: bool = True
    equipment_name: Optional[str] = None
    equipment_brand: Optional[str] = None
    equipment_model: Optional[str] = None
    equipment_power: Optional[str] = None
    customer_complaint: Optional[str] = None
    complaint_official: Optional[str] = None
    likely_diagnosis: Optional[str] = None
    extra_context: Optional[str] = None
    current_meta: Dict[str, Any] = Field(default_factory=dict)


class ManagerRepairActAiDraftResponse(BaseModel):
    repair_meta: Dict[str, str] = Field(default_factory=dict)
    provider: str = "deepseek"
    model: str
    prompt_version: str = "defect_act_v1"


# --- SERVICE ESTIMATES ---

class ManagerEstimateRuleInputPayload(BaseModel):
    rule_id: int
    qty: float = 0.0

    @field_validator("qty")
    @classmethod
    def validate_qty(cls, value: float) -> float:
        if value < 0:
            raise ValueError("qty must be >= 0")
        return value


class ManagerTariffBriefResponse(BaseModel):
    id: int
    service_kind: ManagerTariffServiceKind
    selector_label: str
    estimate_template: str
    category: str
    power_range: str
    base_price: int
    included_route_meters: float


class ManagerInstallEstimateCalculatePayload(BaseModel):
    tariff_id: int
    route_length_m: float = 3.0
    quantity: int = 1
    extra_holes_count: int = 0
    rule_inputs: List[ManagerEstimateRuleInputPayload] = Field(default_factory=list)
    discount_amount: float = 0.0

    @field_validator("route_length_m")
    @classmethod
    def validate_route_length(cls, value: float) -> float:
        if value < 0:
            raise ValueError("route_length_m must be >= 0")
        return value

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be greater than zero")
        return value

    @field_validator("extra_holes_count")
    @classmethod
    def validate_extra_holes_count(cls, value: int) -> int:
        if value < 0:
            raise ValueError("extra_holes_count must be >= 0")
        return value

    @field_validator("discount_amount")
    @classmethod
    def validate_discount_amount(cls, value: float) -> float:
        if value < 0:
            raise ValueError("discount_amount must be >= 0")
        return value


class ManagerInstallEstimateSavePayload(ManagerInstallEstimateCalculatePayload):
    title: Optional[str] = None
    comment: Optional[str] = None
    customer_id: Optional[int] = None
    status: str = "draft"


class ManagerEstimateLineResponse(BaseModel):
    source_type: str
    source_id: Optional[int] = None
    rule_id: Optional[int] = None
    rule_type: Optional[ManagerTariffRuleType] = None
    service_id: Optional[int] = None
    name: str
    qty: float
    unit: str
    unit_price: float
    line_total: float
    sort_order: int = 0


class ManagerInstallEstimateResponse(BaseModel):
    tariff: ManagerTariffBriefResponse
    currency: str = "BYN"
    route_length_m: float
    quantity: int
    lines: List[ManagerEstimateLineResponse]
    rule_lines: List[ManagerEstimateLineResponse]
    subtotal: float
    discount_amount: float
    total: float


class ManagerServiceEstimateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: Optional[int] = None
    tariff: Optional[ManagerTariffBriefResponse] = None
    title: str
    comment: Optional[str] = None
    service_kind: str
    currency: str
    subtotal: float
    discount_amount: float
    total: float
    status: str
    created_by: Optional[str] = None
    created_at: datetime
    lines: List[ManagerEstimateLineResponse] = []
    calculation_payload: Optional[Dict[str, Any]] = None


class ManagerServiceEstimateListResponse(BaseModel):
    items: List[ManagerServiceEstimateResponse]
    total: int
    page: int
    limit: int


class ManagerServiceEstimateOrderLinesMode(str, Enum):
    detailed = "detailed"
    collapsed = "collapsed"


class ManagerServiceEstimateOrderLinesResponse(BaseModel):
    estimate_id: int
    mode: ManagerServiceEstimateOrderLinesMode
    title: str
    services: List[ManagerOrderServiceLinePayload]


# --- MANAGER MAIL ---

class BankReceiptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    operation_type: str
    sender_email: str
    subject: str
    message_id: Optional[str] = None
    fingerprint: str
    email_date: Optional[datetime] = None
    received_at: Optional[datetime] = None
    our_account: Optional[str] = None
    amount: float
    currency: PaymentCurrency
    payer_name: Optional[str] = None
    payer_unp: Optional[str] = None
    payer_account: Optional[str] = None
    payment_document_raw: Optional[str] = None
    payment_document_number: Optional[str] = None
    payment_purpose: Optional[str] = None
    account_balance_after: Optional[float] = None
    parse_error: Optional[str] = None
    matched_order_id: Optional[int] = None
    matched_payment_id: Optional[int] = None
    match_meta: Optional[Dict[str, Any]] = None
    raw_body: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class BankReceiptListResponse(BaseModel):
    items: List[BankReceiptResponse]
    total: int
    page: int
    limit: int


class BankReceiptImportResponse(BaseModel):
    processed: int = 0
    created: int = 0
    duplicates: int = 0
    failed: int = 0
    receipt_ids: List[int] = []


class EmailLeadDecisionResponse(BaseModel):
    status: str
    sender_email: str
    subject: str
    reason: Optional[str] = None
    lead_id: Optional[int] = None
    order_id: Optional[int] = None


class EmailLeadImportResponse(BaseModel):
    processed: int = 0
    scanned_since: Optional[str] = None
    last_import_at: Optional[str] = None
    candidates: int = 0
    ai_checked: int = 0
    would_create: int = 0
    created: int = 0
    duplicates: int = 0
    rejected: int = 0
    failed: int = 0
    lead_ids: List[int] = []
    created_lead_ids: List[int] = []
    order_ids: List[int] = []
    created_order_ids: List[int] = []
    decisions: List[EmailLeadDecisionResponse] = []


class EmailLeadImportJobResponse(BaseModel):
    status: str
    source: Optional[str] = None
    dry_run: bool = False
    lookback_days: Optional[int] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_import_at: Optional[str] = None
    notified_admins: int = 0
    already_running: bool = False
    error: Optional[str] = None
    message: Optional[str] = None
    result: Optional[EmailLeadImportResponse] = None


class BankStatementImportResponse(BaseModel):
    rows: int = 0
    credit_rows: int = 0
    created: int = 0
    matched_existing: int = 0
    skipped: int = 0
    suspicious: int = 0
    receipt_ids: List[int] = []
    created_receipt_ids: List[int] = []
    matched_receipt_ids: List[int] = []
    suspicious_receipt_ids: List[int] = []


class BankReceiptAttachPayload(BaseModel):
    order_id: int
    payment_type: str = "postpayment"


class BankReceiptStatusPayload(BaseModel):
    status: str
    reason: Optional[str] = None


class OutgoingEmailSendPayload(BaseModel):
    to_email: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    reply_to: Optional[str] = None

    @field_validator("to_email")
    @classmethod
    def _validate_to_email(cls, value: str) -> str:
        email = validate_optional_email(value)
        if not email:
            raise ValueError("to_email is required")
        return email

    @field_validator("reply_to")
    @classmethod
    def _validate_optional_mail(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("subject")
    @classmethod
    def _validate_subject(cls, value: str) -> str:
        subject = " ".join(str(value or "").split())
        if not subject:
            raise ValueError("subject is required")
        return subject


class OrderEmailSendPayload(OutgoingEmailSendPayload):
    document_ids: List[int] = Field(default_factory=list)


class OutgoingEmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    recipient_email: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
