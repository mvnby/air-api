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
from models import PaymentCurrency

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


class OrderProductLineResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    product_title: str
    quantity: int
    price: int
    cost: int
    is_installation_included: bool
    installation_price: int
    line_total: int


class OrderServiceLineResponse(BaseModel):
    id: int
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
        return self.proposal_status == "approved"

    # Financials
    total_payments: float = 0.0
    balance_due: float = 0.0


class ManagerOrderDocumentItem(BaseModel):
    id: int
    doc_type: str
    number: str
    date: datetime
    edit_url: str


class ManagerOrderDocumentListResponse(BaseModel):
    items: List[ManagerOrderDocumentItem]


class ManagerCustomerDocumentItem(BaseModel):
    id: int
    order_id: int
    doc_type: str
    number: str
    date: datetime
    edit_url: str


class ManagerCustomerDocumentListResponse(BaseModel):
    items: List[ManagerCustomerDocumentItem]


class PaymentCreatePayload(BaseModel):
    amount: float
    currency: PaymentCurrency = PaymentCurrency.BYN
    type: str # prepayment or postpayment
    comment: Optional[str] = None


class PaymentResponse(BaseModel):
    id: int
    amount: float
    currency: PaymentCurrency
    date: datetime
    type: str
    comment: Optional[str] = None
    created_at: datetime



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



class ManagerOrderDetailResponse(ManagerOrderListItemResponse):
    product_lines: List[OrderProductLineResponse] = []
    service_lines: List[OrderServiceLineResponse] = []
    documents: List[ManagerOrderDocumentItem] = []
    payments: List[PaymentResponse] = []
    work_stages: List[OrderWorkStageResponse] = []


class ManagerOrderListResponse(BaseModel):
    items: List[ManagerOrderListItemResponse]
    meta: Meta


class ManagerOrderProductLinePayload(BaseModel):
    link_id: Optional[int] = None
    product_id: int
    quantity: int
    price: int
    cost: Optional[int] = None


class ManagerOrderServiceLinePayload(BaseModel):
    link_id: Optional[int] = None
    service_id: Optional[int] = None
    title: str
    quantity: int
    price: int
    cost: Optional[int] = None


class ManagerOrderUpdatePayload(BaseModel):
    status: Optional[str] = None
    next_followup_date: Optional[datetime] = None
    measurement_date: Optional[datetime] = None
    installation_date: Optional[datetime] = None
    comment: Optional[str] = None
    no_answer_at: Optional[str] = None

    # Negotiation
    measurement_required: Optional[bool] = None
    measurer_id: Optional[int] = None
    measurement_result: Optional[str] = None
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
    doc_type: str
    edit_url: str


class DocumentTemplateItem(BaseModel):
    id: str
    name: str


class DocumentTemplateListResponse(BaseModel):
    items: List[DocumentTemplateItem]




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

# --- DASHBOARD STATS ---

class DashboardTouchpoint(BaseModel):
    order_id: int
    customer_name: str
    phone: Optional[str] = None
    next_followup_date: datetime
    title: Optional[str] = None

class DashboardStatsResponse(BaseModel):
    total_amount: float
    new_leads_count: int
    upcoming_touchpoints: List[DashboardTouchpoint]


# --- LEADS INBOX ---

class LeadsCounterResponse(BaseModel):
    count: int
    has_new: bool


class LeadsInboxItemResponse(BaseModel):
    id: int
    status: str
    is_new: bool
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    comment: Optional[str] = None
    no_answer_at: Optional[datetime] = None
    created_at: datetime
    customer_type: str = "individual"
    customer_inn: Optional[str] = None
    customer_full_legal_name: Optional[str] = None


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

class ManagerTariffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    category: str
    power_range: str
    base_price: int
    extra_pipe_price: int
    included_pipe_meters: int
    is_fixed: bool
    comment: Optional[str]


class ManagerTariffCreatePayload(BaseModel):
    category: str
    power_range: str = ""
    base_price: int = 0
    extra_pipe_price: int = 0
    included_pipe_meters: int = 3
    is_fixed: bool = True
    comment: Optional[str] = None


class ManagerTariffUpdatePayload(BaseModel):
    category: Optional[str] = None
    power_range: Optional[str] = None
    base_price: Optional[int] = None
    extra_pipe_price: Optional[int] = None
    included_pipe_meters: Optional[int] = None
    is_fixed: Optional[bool] = None
    comment: Optional[str] = None


class ManagerTariffListResponse(BaseModel):
    items: List[ManagerTariffResponse]
