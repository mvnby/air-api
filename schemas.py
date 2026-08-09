from typing import Annotated, List, Optional, Any, Dict, Literal
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from enum import Enum
from core.input_validation import (
    validate_optional_bic,
    validate_optional_email,
    validate_optional_iban,
    validate_optional_phone,
    validate_optional_unp,
    validate_public_manual_url,
)
from models import EquipmentServiceEventType, PaymentCurrency
from schemas_public_checkout import (
    CartItemPayload,
    CustomerPayload,
    InstallationMetaPayload,
    OrderPayload,
    OrderResponse,
    PublicContactLeadPayload,
    PublicContactLeadResponse,
    PublicOrderPricingErrorResponse,
)
from schemas_features import ManagerProductFeatureWorkspaceResponse, PublicFeatureResponse
from schemas_brand_series import (
    ProductSeriesBrandFeatureResponse,
    ProductSeriesContentBlockResponse,
    ProductSeriesFeatureBlockResponse,
)
from schemas_installation_estimate import (
    InstallationEstimateLeadPayload,
    InstallationEstimateLeadResponse,
)
from schemas_catalog import CatalogRevisionResponse
from schemas_common import Meta
from schemas_manager_installers import (
    ManagerInstallerBase,
    ManagerInstallerCreatePayload,
    ManagerInstallerListResponse,
    ManagerInstallerResponse,
    ManagerInstallerUpdatePayload,
)
from schemas_manager_leads import (
    LeadCreatePayload,
    LeadListResponse,
    LeadLossPayload,
    LeadQualifyPayload,
    LeadQualifyResponse,
    LeadResponse,
    LeadUpdatePayload,
    ProductAvailabilityLeadPayload,
    ProductAvailabilityLeadResponse,
)
from schemas_manager_orders import (
    CalendarEventResponse,
    CalendarEventType,
    ManagerCustomerDocumentItem,
    ManagerCustomerDocumentListResponse,
    ManagerCustomerReconciliationBasisDocument,
    ManagerCustomerReconciliationDocumentItem,
    ManagerCustomerReconciliationDocumentResponse,
    ManagerCustomerReconciliationPaymentItem,
    ManagerCustomerReconciliationResponse,
    ManagerOrderCreatePayload,
    ManagerOrderDetailResponse,
    ManagerOrderDocumentGeneratePayload,
    ManagerOrderDocumentItem,
    ManagerOrderDocumentListResponse,
    ManagerOrderDocumentResponse,
    ManagerOrderExportRequest,
    ManagerOrderListItemResponse,
    ManagerOrderListResponse,
    ManagerOrderProductLinePayload,
    ManagerOrderServiceLinePayload,
    ManagerOrderUpdatePayload,
    ManagerStaleWorkStageItem,
    ManagerStaleWorkStageListResponse,
    OrderCustomerBranchBrief,
    OrderCustomerBrief,
    OrderCustomerContractBrief,
    OrderProductLineResponse,
    OrderProductLogisticsComponent,
    OrderProposalCreatePayload,
    OrderProposalListResponse,
    OrderProposalResponse,
    OrderProposalUpdatePayload,
    OrderServiceLineResponse,
    OrderWorkStageCreatePayload,
    OrderWorkStageResponse,
    OrderWorkStageUpdatePayload,
    PaymentBankReceiptResponse,
    PaymentCreatePayload,
    PaymentResponse,
    ProductLogisticsComponentTemplate,
)
from schemas_manager_order_transfer import (
    ManagerOrderImportCommitRequest,
    ManagerOrderImportCommitResponse,
    ManagerOrderImportCustomerMatch,
    ManagerOrderImportPreviewRequest,
    ManagerOrderImportPreviewResponse,
    ManagerOrderImportProductMatch,
    ManagerOrderTransferCustomer,
    ManagerOrderTransferCustomerBranch,
    ManagerOrderTransferOrder,
    ManagerOrderTransferPackage,
    ManagerOrderTransferPayment,
    ManagerOrderTransferProductLine,
    ManagerOrderTransferProductRef,
    ManagerOrderTransferProposal,
    ManagerOrderTransferServiceLine,
    ManagerOrderTransferServiceRef,
    ManagerOrderTransferWorkStage,
)

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

class ManagerMediaAssetResponse(BaseModel):
    id: int
    parent_asset_id: Optional[int] = None
    title: str
    alt_text: Optional[str] = None
    description: Optional[str] = None
    kind: str
    tags: List[str] = []
    variant_type: str
    url: str
    original_url: Optional[str] = None
    source_filename: Optional[str] = None
    mime_type: str
    storage_provider: str
    processing_status: str
    processing_error: Optional[str] = None
    content_hash: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: int = 0
    usage_count: int = 0
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ManagerMediaAssetListResponse(BaseModel):
    items: List[ManagerMediaAssetResponse]
    meta: Meta


class ManagerMediaAssetUpdatePayload(BaseModel):
    title: Optional[str] = None
    alt_text: Optional[str] = None
    description: Optional[str] = None
    kind: Optional[str] = None
    tags: Optional[List[str]] = None


class ManagerMediaAssetCropPayload(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    title: Optional[str] = None


class ManagerMediaAssetUrlUploadPayload(BaseModel):
    url: str
    kind: str = "misc"
    tags: List[str] = []


class ManagerMediaAssetUploadResponse(BaseModel):
    uploaded: int
    items: List[ManagerMediaAssetResponse]


class ManagerMediaBackfillReferencedAssetsResponse(BaseModel):
    dry_run: bool
    include_remote: bool
    limit: int
    references_seen: int
    unique_urls_seen: int
    planned: int
    created: int
    skipped_count: int
    items: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []


class ManagerMediaProcessingJobCreatePayload(BaseModel):
    operation: str = "background_removal"
    provider: Optional[str] = "rembg"
    rembg_model: Optional[str] = None
    options: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10000)


class ManagerMediaProcessingJobResponse(BaseModel):
    job_id: str
    source_asset_id: int
    result_asset_id: Optional[int] = None
    operation: str
    status: str
    stage: str
    provider: Optional[str] = None
    rembg_model: Optional[str] = None
    priority: int
    attempts: int
    worker_id: Optional[str] = None
    request_payload: Dict[str, Any] = Field(default_factory=dict)
    result_payload: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    source_url: Optional[str] = None
    source_title: Optional[str] = None
    result_url: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    lease_expires_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    updated_at: datetime


class ManagerMediaProcessingJobListResponse(BaseModel):
    items: List[ManagerMediaProcessingJobResponse]
    meta: Meta


class MediaWorkerClaimPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    worker_id: str = Field(min_length=1, max_length=128)
    capabilities: List[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list,
        max_length=32,
    )
    lease_seconds: int = Field(default=900, ge=60, le=86400)


class MediaWorkerClaimedJobResponse(ManagerMediaProcessingJobResponse):
    lease_token: str


class MediaWorkerClaimResponse(BaseModel):
    job: Optional[MediaWorkerClaimedJobResponse] = None


class MediaWorkerRenewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    worker_id: str = Field(min_length=1, max_length=128)
    lease_token: str = Field(min_length=32, max_length=256)
    lease_seconds: int = Field(default=900, ge=60, le=86400)


class MediaWorkerFailPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    worker_id: str = Field(min_length=1, max_length=128)
    lease_token: str = Field(min_length=32, max_length=256)
    error: str = Field(min_length=1, max_length=2000)


class ManagerBackgroundRemovalModelOption(BaseModel):
    value: str
    label: str
    description: str = ""
    recommended: bool = False


class ManagerBackgroundRemovalProviderOption(BaseModel):
    value: str
    label: str
    description: str = ""


class ManagerBackgroundRemovalConfigResponse(BaseModel):
    default_provider: str
    default_rembg_model: str
    rembg_process_mode: str
    preload_models: List[str]
    provider_options: List[ManagerBackgroundRemovalProviderOption]
    rembg_models: List[ManagerBackgroundRemovalModelOption]

# --- CATALOG ---

ProductKind = Literal[
    "unknown",
    "complete_split_system",
    "indoor_unit",
    "outdoor_unit",
    "panel",
    "accessory",
    "consumable",
    "other",
]
PublicStockState = Literal[
    "local_stock",
    "supplier_stock",
    "available_to_order",
    "out_of_stock",
]


class ProductBase(BaseModel):
    id: int
    title: str
    slug: Optional[str]
    price: int
    old_price: Optional[int]
    product_kind: ProductKind = "unknown"
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

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        return validate_public_manual_url(value)


class ProductSiblingResponse(BaseModel):
    id: int
    title: str
    slug: Optional[str]
    price: int
    old_price: Optional[int]
    specs: Dict[str, Any] = Field(default_factory=dict)
    is_inverter: bool
    main_image: Optional[str]


class ProductBrandResponse(BaseModel):
    id: int
    title: str
    slug: str
    logo_url: Optional[str] = None


class ProductSeriesResponse(BaseModel):
    id: int
    title: str
    slug: str
    tagline: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    hero_image: Optional[str] = None
    gallery_images: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    brand_features: List[ProductSeriesBrandFeatureResponse] = Field(default_factory=list)
    catalog_features: List[PublicFeatureResponse] = Field(default_factory=list)
    feature_blocks: List[ProductSeriesFeatureBlockResponse] = Field(default_factory=list)
    content_blocks: List[ProductSeriesContentBlockResponse] = Field(default_factory=list)
    footnotes: List[str] = Field(default_factory=list)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    source_url: Optional[str] = None


class ProductSeriesNavigationItemResponse(BaseModel):
    series: Optional[ProductSeriesResponse] = None
    series_siblings: List[ProductSiblingResponse] = []


class ProductSeriesNavigationResponse(BaseModel):
    products: Dict[str, ProductSeriesNavigationItemResponse] = {}


class ProductResponse(ProductBase):
    vitebsk_qty: int = 0
    minsk_qty: int = 0
    availability_status: Optional[str] = None
    public_stock_state: Optional[PublicStockState] = None
    delivery_min_days: Optional[int] = None
    delivery_max_days: Optional[int] = None
    brand: Optional[ProductBrandResponse] = None
    series: Optional[ProductSeriesResponse] = None
    tags: List[TagResponse] = []
    specs: Dict[str, Any] = {}
    images: List[str] = [] # Legacy
    gallery_images: List[ProductImageResponse] = [] # New
    manuals: List[ProductManualResponse] = []
    series_siblings: List[ProductSiblingResponse] = []
    features: List[PublicFeatureResponse] = []


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


class WebRebuildStatusResponse(BaseModel):
    current_revision: int
    current_revision_updated_at: datetime
    published_revision: int
    published_at: Optional[datetime] = None
    requested_revision: Optional[int] = None
    requested_at: Optional[datetime] = None
    needs_rebuild: bool
    state: str
    last_error: Optional[str] = None


class WebRebuildTriggerResponse(WebRebuildStatusResponse):
    message: str


class WebRebuildCompletePayload(BaseModel):
    catalog_revision: int
    status: str = "success"
    error: Optional[str] = None


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


class SpecRegistryItemResponse(BaseModel):
    key: str
    label: str
    value_type: str
    quantity_kind: Optional[str] = None
    canonical_unit: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    enum_values: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    manager_note: Optional[str] = None


class SpecRegistryResponse(BaseModel):
    items: List[SpecRegistryItemResponse]
    total: int


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


class PublicFeaturedSeriesResponse(BaseModel):
    name: str
    slug: str
    sort_order: int


class PublicBrandResponse(BaseModel):
    id: int
    title: str
    slug: str
    logo_url: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    products_count: int
    sort_order: int
    featured_series: List[PublicFeaturedSeriesResponse] = Field(default_factory=list)


class PublicBrandDetailResponse(PublicBrandResponse):
    features: List[ProductSeriesBrandFeatureResponse] = Field(default_factory=list)


class PublicRelatedSeriesResponse(BaseModel):
    title: str
    slug: str
    short_description: Optional[str] = None
    hero_image: Optional[str] = None
    products_count: int = 0


class PublicSeriesPageResponse(BaseModel):
    brand: ProductBrandResponse
    series: ProductSeriesResponse
    products: List[ProductResponse] = Field(default_factory=list)
    related_series: List[PublicRelatedSeriesResponse] = Field(default_factory=list)

# --- STAFF USERS ---

class ManagerStaffBase(BaseModel):
    display_name: str
    status: str = "active"
    primary_role: str = "installer"
    username: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    is_assignable_installer: bool = False
    default_rate: Optional[float] = None


class ManagerStaffCreatePayload(ManagerStaffBase):
    password: Optional[str] = None


class ManagerStaffUpdatePayload(BaseModel):
    display_name: Optional[str] = None
    status: Optional[str] = None
    primary_role: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    is_assignable_installer: Optional[bool] = None
    default_rate: Optional[float] = None


class ManagerStaffResponse(ManagerStaffBase):
    id: int
    has_password: bool = False
    legacy_installer_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class ManagerStaffListResponse(BaseModel):
    items: List[ManagerStaffResponse]
    meta: Meta


class TelegramLoginPayload(BaseModel):
    id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


# --- DOCUMENT TEMPLATES ---

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




# --- MANAGER AUTH ---

class ManagerAuthStatusResponse(BaseModel):
    username: str
    status: str
    staff_user_id: Optional[int] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    auth_source: str = "legacy"
    tenant_id: int
    storefront_id: int
    tenant_membership_id: Optional[int] = None


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
    product_kind: ProductKind = "unknown"
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
    features_workspace: Optional[ManagerProductFeatureWorkspaceResponse] = None


class ManagerCatalogProductListResponse(BaseModel):
    items: List[ManagerCatalogProductItemResponse]
    meta: Meta


class ManagerCatalogQualityIssueResponse(BaseModel):
    code: str
    label: str
    category: str
    severity: Literal["critical", "warning", "info"]
    message: str
    detail: Optional[str] = None


class ManagerCatalogQualitySummaryItemResponse(BaseModel):
    code: str
    label: str
    category: str
    severity: Literal["critical", "warning", "info"]
    count: int


class ManagerCatalogQualityCategoryResponse(BaseModel):
    category: str
    label: str
    count: int
    critical: int = 0
    warning: int = 0
    info: int = 0


class ManagerCatalogQualityFilterOptionResponse(BaseModel):
    value: str
    label: str
    count: int = 0
    parent_value: Optional[str] = None


class ManagerCatalogQualityFilterOptionsResponse(BaseModel):
    equipment_types: List[ManagerCatalogQualityFilterOptionResponse] = Field(default_factory=list)
    equipment_subtypes: List[ManagerCatalogQualityFilterOptionResponse] = Field(default_factory=list)
    brands: List[ManagerCatalogQualityFilterOptionResponse] = Field(default_factory=list)
    series: List[ManagerCatalogQualityFilterOptionResponse] = Field(default_factory=list)
    suppliers: List[ManagerCatalogQualityFilterOptionResponse] = Field(default_factory=list)


class ManagerCatalogQualitySupplierResponse(BaseModel):
    supplier_id: int
    supplier_name: str
    qty: int = 0
    rrc_byn: Optional[float] = None
    wholesale_value: Optional[float] = None
    wholesale_currency: Optional[str] = None
    updated_at: Optional[datetime] = None


class ManagerCatalogQualityGroupResponse(BaseModel):
    key: str
    label: str
    count: int
    average_score: int
    critical_products: int = 0
    in_stock_products: int = 0
    media_problem_products: int = 0
    spec_problem_products: int = 0
    shared_main_image_products: int = 0
    shared_main_image_width: Optional[int] = None
    shared_main_image_height: Optional[int] = None


class ManagerCatalogQualityProductResponse(BaseModel):
    product_id: int
    title: str
    slug: Optional[str] = None
    brand_id: Optional[int] = None
    brand_title: Optional[str] = None
    series_id: Optional[int] = None
    series_title: Optional[str] = None
    equipment_type: Optional[str] = None
    equipment_type_label: Optional[str] = None
    equipment_subtype: Optional[str] = None
    equipment_subtype_label: Optional[str] = None
    main_image: Optional[str] = None
    price: int = 0
    is_published: bool = True
    score: int
    issue_count: int
    image_count: int = 0
    main_image_width: Optional[int] = None
    main_image_height: Optional[int] = None
    media_status: str = "unknown"
    supplier_mapping_count: int = 0
    suppliers: List[ManagerCatalogQualitySupplierResponse] = Field(default_factory=list)
    available_qty: int = 0
    created_at: Optional[datetime] = None
    critical_issue_count: int = 0
    fixable_issue_count: int = 0
    work_priority: Literal["high", "medium", "low"] = "low"
    priority_reason: str = ""
    group_key: Optional[str] = None
    group_label: Optional[str] = None
    issues: List[ManagerCatalogQualityIssueResponse] = Field(default_factory=list)


class ManagerCatalogQualityReportResponse(BaseModel):
    generated_at: datetime
    total_products: int
    problem_products: int
    critical_products: int
    fixable_products: int
    average_score: int
    items: List[ManagerCatalogQualityProductResponse]
    summary: List[ManagerCatalogQualitySummaryItemResponse]
    categories: List[ManagerCatalogQualityCategoryResponse]
    groups: List[ManagerCatalogQualityGroupResponse] = Field(default_factory=list)
    filter_options: ManagerCatalogQualityFilterOptionsResponse
    builtin_view_counts: Dict[str, int] = Field(default_factory=dict)
    severity_issue_counts: Dict[str, int] = Field(default_factory=dict)
    severity_product_counts: Dict[str, int] = Field(default_factory=dict)
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
    maintenance_provider: Optional[Literal["mvn", "authorized", "external"]] = None
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


class ManagerEquipmentComponentItemResponse(BaseModel):
    id: int
    equipment_id: int
    catalog_product_id: Optional[int] = None
    supplier_id: Optional[int] = None
    component_type: str = "other"
    title: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    supplier_invoice_number: Optional[str] = None
    supplier_invoice_date: Optional[datetime] = None
    notes: Optional[str] = None
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None


class ManagerEquipmentItemResponse(BaseModel):
    id: int
    customer_id: int
    customer_branch_id: Optional[int] = None
    catalog_product_id: Optional[int] = None
    source_order_id: Optional[int] = None
    equipment_type: str = "hvac"
    equipment_source: str = "unknown"
    display_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = None
    installed_at: Optional[datetime] = None
    commissioned_at: Optional[datetime] = None
    warranty_started_at: Optional[datetime] = None
    warranty_expires_at: Optional[datetime] = None
    warranty_terms: Optional[str] = None
    warranty_status: str = "unknown"
    notes: Optional[str] = None
    is_archived: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    branch_name: Optional[str] = None
    branch_address: Optional[str] = None
    service_contact_name: Optional[str] = None
    service_contact_phone: Optional[str] = None
    last_service_at: Optional[datetime] = None
    next_maintenance_due_at: Optional[datetime] = None
    attention_reasons: List[str] = Field(default_factory=list)


class ManagerEquipmentDetailResponse(ManagerEquipmentItemResponse):
    components: List[ManagerEquipmentComponentItemResponse] = Field(default_factory=list)
    recent_history: List[ManagerEquipmentServiceHistoryItemResponse] = Field(default_factory=list)
    coverages: List["ManagerEquipmentWarrantyCoverageResponse"] = Field(default_factory=list)
    linked_orders: List["ManagerEquipmentLinkedOrderResponse"] = Field(default_factory=list)


class ManagerEquipmentWarrantyCoverageResponse(BaseModel):
    id: int
    equipment_id: int
    component_id: Optional[int] = None
    policy_id: Optional[int] = None
    coverage_type: str
    source: str
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    maintenance_required: bool = False
    maintenance_interval_months: Optional[int] = None
    grace_period_days: int = 0
    allowed_maintenance_provider: str = "any"
    next_maintenance_due_at: Optional[datetime] = None
    terms_snapshot: Optional[str] = None
    policy_snapshot: Dict[str, Any] = Field(default_factory=dict)
    decision_status: str = "none"
    decision_reason: Optional[str] = None
    decided_at: Optional[datetime] = None
    decided_by: Optional[str] = None
    time_status: str = "unknown"
    maintenance_status: str = "unknown"
    requires_manager_decision: bool = False
    created_at: datetime
    updated_at: datetime


class ManagerEquipmentLinkedOrderResponse(BaseModel):
    order_id: int
    role: str
    title: str
    status: str
    created_at: datetime


class ManagerOrderEquipmentLinkCreatePayload(BaseModel):
    equipment_id: int
    role: str = "other"


class ManagerOrderEquipmentLinkItemResponse(BaseModel):
    link_id: Optional[int] = None
    role: str
    legacy_source_link: bool = False
    equipment: ManagerEquipmentDetailResponse


class ManagerOrderEquipmentLinkListResponse(BaseModel):
    items: List[ManagerOrderEquipmentLinkItemResponse] = Field(default_factory=list)
    total: int = 0


class ManagerEquipmentListResponse(BaseModel):
    items: List[ManagerEquipmentItemResponse]
    meta: Meta


class ManagerEquipmentServiceHistoryListResponse(BaseModel):
    items: List[ManagerEquipmentServiceHistoryItemResponse]
    meta: Meta


class ManagerEquipmentComponentCreatePayload(BaseModel):
    catalog_product_id: Optional[int] = None
    supplier_id: Optional[int] = None
    component_type: Optional[str] = "other"
    title: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    supplier_invoice_number: Optional[str] = None
    supplier_invoice_date: Optional[datetime] = None
    notes: Optional[str] = None
    is_archived: bool = False

    @field_validator(
        "component_type",
        "title",
        "brand",
        "model",
        "serial",
        "inventory_number",
        "supplier_invoice_number",
        "notes",
    )
    @classmethod
    def _trim_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ManagerEquipmentComponentUpdatePayload(BaseModel):
    catalog_product_id: Optional[int] = None
    supplier_id: Optional[int] = None
    component_type: Optional[str] = None
    title: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    supplier_invoice_number: Optional[str] = None
    supplier_invoice_date: Optional[datetime] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None

    @field_validator(
        "component_type",
        "title",
        "brand",
        "model",
        "serial",
        "inventory_number",
        "supplier_invoice_number",
        "notes",
    )
    @classmethod
    def _trim_string_fields(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class ManagerEquipmentFromOrderPayload(BaseModel):
    supplier_id: Optional[int] = None
    warranty_start_date: Optional[datetime] = None
    work_warranty_months: Optional[int] = Field(default=None, ge=0, le=120)
    work_warranty_terms: Optional[str] = None
    order_role: str = "sale"
    include_component_placeholders: bool = True


class ManagerEquipmentFromOrderResponse(BaseModel):
    items: List[ManagerEquipmentDetailResponse] = Field(default_factory=list)
    created_count: int = 0
    skipped_count: int = 0


class ManagerEquipmentCreatePayload(BaseModel):
    customer_id: int
    customer_branch_id: Optional[int] = None
    catalog_product_id: Optional[int] = None
    source_order_id: Optional[int] = None
    supplier_id: Optional[int] = None
    order_role: str = "other"
    work_warranty_months: Optional[int] = Field(default=None, ge=0, le=120)
    work_warranty_terms: Optional[str] = None
    equipment_type: Optional[str] = "hvac"
    equipment_source: Optional[str] = "unknown"
    display_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = None
    installed_at: Optional[datetime] = None
    commissioned_at: Optional[datetime] = None
    warranty_started_at: Optional[datetime] = None
    warranty_expires_at: Optional[datetime] = None
    warranty_terms: Optional[str] = None
    notes: Optional[str] = None
    is_archived: bool = False

    @field_validator(
        "equipment_type",
        "equipment_source",
        "display_name",
        "brand",
        "model",
        "serial",
        "inventory_number",
        "location_hint",
        "refrigerant_type",
        "warranty_terms",
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
    catalog_product_id: Optional[int] = None
    source_order_id: Optional[int] = None
    equipment_type: Optional[str] = None
    equipment_source: Optional[str] = None
    display_name: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial: Optional[str] = None
    inventory_number: Optional[str] = None
    location_hint: Optional[str] = None
    refrigerant_type: Optional[str] = None
    installed_at: Optional[datetime] = None
    commissioned_at: Optional[datetime] = None
    warranty_started_at: Optional[datetime] = None
    warranty_expires_at: Optional[datetime] = None
    warranty_terms: Optional[str] = None
    notes: Optional[str] = None
    is_archived: Optional[bool] = None

    @field_validator(
        "equipment_type",
        "equipment_source",
        "display_name",
        "brand",
        "model",
        "serial",
        "inventory_number",
        "location_hint",
        "refrigerant_type",
        "warranty_terms",
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
    maintenance_provider: Optional[Literal["mvn", "authorized", "external"]] = None
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


class ManagerServiceAttachmentItemResponse(BaseModel):
    id: Optional[int] = None
    legacy_key: Optional[str] = None
    legacy: bool = False
    file_kind: str = "other"
    category: str = "other"
    filename: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    caption: Optional[str] = None
    transcript: Optional[str] = None
    source: str = "manager"
    processing_status: str = "ready"
    processing_error: Optional[str] = None
    captured_at: Optional[datetime] = None
    created_at: datetime
    preview_available: bool = False
    equipment_id: Optional[int] = None
    component_id: Optional[int] = None
    service_history_id: Optional[int] = None


class ManagerServiceAttachmentListResponse(BaseModel):
    items: List[ManagerServiceAttachmentItemResponse] = Field(default_factory=list)
    total: int = 0


class ManagerServiceAttachmentUpdatePayload(BaseModel):
    order_id: Optional[int] = None
    category: Optional[str] = None
    caption: Optional[str] = None
    transcript: Optional[str] = None
    equipment_id: Optional[int] = None
    component_id: Optional[int] = None
    service_history_id: Optional[int] = None


class ManagerServiceAttachmentAccessResponse(BaseModel):
    url: str
    expires_at: datetime
    variant: str


class ManagerWarrantyPolicyResponse(BaseModel):
    id: int
    name: str
    coverage_type: str = "supplier"
    supplier_id: Optional[int] = None
    brand_id: Optional[int] = None
    series_id: Optional[int] = None
    product_id: Optional[int] = None
    supplier_name: Optional[str] = None
    brand_title: Optional[str] = None
    series_title: Optional[str] = None
    series_brand_id: Optional[int] = None
    product_title: Optional[str] = None
    duration_months: Optional[int] = None
    start_event: str = "commissioning"
    maintenance_required: bool = False
    maintenance_interval_months: Optional[int] = None
    grace_period_days: int = 0
    allowed_maintenance_provider: str = "any"
    terms: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_until: Optional[datetime] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class ManagerWarrantyPolicyPayload(BaseModel):
    name: Optional[str] = None
    coverage_type: Optional[str] = None
    supplier_id: Optional[int] = None
    brand_id: Optional[int] = None
    series_id: Optional[int] = None
    product_id: Optional[int] = None
    duration_months: Optional[int] = None
    start_event: Optional[str] = None
    maintenance_required: Optional[bool] = None
    maintenance_interval_months: Optional[int] = None
    grace_period_days: Optional[int] = None
    allowed_maintenance_provider: Optional[str] = None
    terms: Optional[str] = None
    effective_from: Optional[datetime] = None
    effective_until: Optional[datetime] = None
    is_active: Optional[bool] = None


class ManagerWarrantyPolicyListResponse(BaseModel):
    items: List[ManagerWarrantyPolicyResponse] = Field(default_factory=list)


class ManagerWarrantyDecisionPayload(BaseModel):
    action: Literal["voided", "restored"]
    reason: str


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


class CustomerRequisitesExtractedData(BaseModel):
    name: Optional[str] = None
    full_legal_name: Optional[str] = None
    inn: Optional[str] = None
    legal_address: Optional[str] = None
    bank_name: Optional[str] = None
    bic: Optional[str] = None
    iban: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    phone_raw: Optional[str] = None
    signer_position: Optional[str] = None
    signer_name: Optional[str] = None
    acting_basis: Optional[str] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class CustomerRequisitesDuplicateCustomer(BaseModel):
    id: int
    name: Optional[str] = None
    inn: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class CustomerRequisitesRecognitionResponse(BaseModel):
    id: int
    status: str
    source: str
    raw_text: str
    extracted: CustomerRequisitesExtractedData
    validation_flags: Dict[str, Any] = Field(default_factory=dict)
    duplicate_customer: Optional[CustomerRequisitesDuplicateCustomer] = None
    confirmed_customer_id: Optional[int] = None
    confirmed_action: Optional[str] = None
    local_file_url: Optional[str] = None
    created_at: datetime


class CustomerRequisitesConfirmPayload(BaseModel):
    action: str
    customer_id: Optional[int] = None

    @field_validator("action")
    @classmethod
    def _validate_action(cls, value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"create", "update"}:
            raise ValueError("action must be create or update")
        return normalized


class CustomerRequisitesConfirmResponse(BaseModel):
    recognition: CustomerRequisitesRecognitionResponse
    customer: ManagerCatalogCustomerItemResponse


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
    short_description: Optional[str] = None
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
    short_description: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    is_published: bool = True
    sort_order: int = 0


class ManagerBrandUpdatePayload(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    short_description: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = None
    is_published: Optional[bool] = None
    sort_order: Optional[int] = None


class ManagerSeriesGalleryApplyPayload(BaseModel):
    source_urls: List[str]


class ManagerBrandFeatureResponse(ProductSeriesBrandFeatureResponse):
    brand_id: int
    created_at: datetime
    updated_at: datetime
    series_count: int = 0


class ManagerBrandFeatureListResponse(BaseModel):
    items: List[ManagerBrandFeatureResponse]


class ManagerBrandFeatureCreatePayload(BaseModel):
    title: str
    slug: Optional[str] = None
    text: Optional[str] = None
    image_url: Optional[str] = None
    icon: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    is_published: bool = True
    sort_order: int = 0


class ManagerBrandFeatureUpdatePayload(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    text: Optional[str] = None
    image_url: Optional[str] = None
    icon: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: Optional[List[str]] = None
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


class ProductImageCropPayload(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mode: Literal["append", "replace"] = "append"
    set_main: bool = False


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


class ManagerSeriesGalleryApplyResponse(ManagerMediaBulkAddResponse):
    series_id: int
    images_applied: int


class ManagerMediaBulkDeleteResponse(ManagerActionMessageResponse):
    products_count: int
    deleted_links: int


class ManagerMediaBulkUploadResponse(ManagerActionMessageResponse):
    products_count: int
    files_count: int
    uploaded_links: int


class ManagerMediaApplySeriesResponse(ManagerActionMessageResponse):
    dry_run: bool = False
    source_product_id: int
    series_id: int
    series_title: Optional[str] = None
    updated_products: int
    images_applied: int
    main_image: Optional[str] = None
    replaced_links: int = 0
    obsolete_urls: List[str] = Field(default_factory=list)
    preserved_installation_links: int = 0
    deleted_files_count: int = 0


class ManagerMediaUploadLocalImagesResponse(BaseModel):
    uploaded: int
    images: List[ManagerMediaImageLinkResponse]


class ManagerMediaCleanupResponse(BaseModel):
    dry_run: bool
    deleted_count: int
    reclaimed_bytes: int
    files: List[str]


class ProductMainImageCleanupBatchResponse(BaseModel):
    id: Optional[int] = None
    status: str
    requested_limit: int
    processor_method: str
    processor_version: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class ProductMainImageCleanupItemResponse(BaseModel):
    id: Optional[int] = None
    batch_id: Optional[int] = None
    product_id: int
    product_title: Optional[str] = None
    product_slug: Optional[str] = None
    product_brand_id: Optional[int] = None
    product_brand_title: Optional[str] = None
    product_series_id: Optional[int] = None
    product_series_title: Optional[str] = None
    product_model: Optional[str] = None
    product_current_main_image: Optional[str] = None
    source_product_image_id: Optional[int] = None
    original_image_url: str
    candidate_image_url: Optional[str] = None
    approved_image_url: Optional[str] = None
    status: str
    skip_reason: Optional[str] = None
    reject_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    processor_method: Optional[str] = None
    processor_version: Optional[str] = None
    confidence_score: Optional[float] = None
    quality_score: Optional[float] = None
    candidate_storage_provider: Optional[str] = None
    candidate_content_hash: Optional[str] = None
    candidate_width: Optional[int] = None
    candidate_height: Optional[int] = None
    approved_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    approved_at: Optional[datetime] = None


class ProductMainImageCleanupSkippedExistingResponse(BaseModel):
    product_id: int
    original_image_url: str
    reason: str
    existing_item_id: Optional[int] = None
    existing_status: Optional[str] = None


class ProductMainImageCleanupBatchCreatePayload(BaseModel):
    limit: int = Field(default=50, ge=1, le=50)
    processor_method: str = "noop"


class ProductMainImageCleanupBatchCreateResponse(BaseModel):
    batch: ProductMainImageCleanupBatchResponse
    items: List[ProductMainImageCleanupItemResponse] = []
    created_count: int
    candidate_ready_count: int
    skipped_count: int
    failed_count: int
    already_processed_count: int
    skipped_existing: List[ProductMainImageCleanupSkippedExistingResponse] = []


class ProductMainImageCleanupBatchListResponse(BaseModel):
    items: List[ProductMainImageCleanupBatchResponse] = []


class ProductMainImageCleanupItemListResponse(BaseModel):
    items: List[ProductMainImageCleanupItemResponse] = []


class ProductMainImageCleanupApprovePayload(BaseModel):
    item_ids: List[int] = Field(default_factory=list)


class ProductMainImageCleanupRejectPayload(BaseModel):
    item_ids: List[int] = Field(default_factory=list)
    reason: str


class ProductMainImageCleanupSkipPayload(BaseModel):
    item_ids: List[int] = Field(default_factory=list)
    reason: str


class ProductMainImageCleanupDecisionResponse(BaseModel):
    updated_count: int
    skipped_count: int
    skipped: List[Dict[str, Any]] = []
    items: List[ProductMainImageCleanupItemResponse] = []


class ProductMainImageCleanupSkipReasonsResponse(BaseModel):
    items: List[str] = []


class ProductUpdate(BaseModel):
    title: Optional[str] = None
    price: Optional[int] = None
    old_price: Optional[int] = None
    product_kind: Optional[ProductKind] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    is_inverter: Optional[bool] = None
    power_cooling: Optional[float] = None
    main_image: Optional[str] = None
    source_url: Optional[str] = None
    specs: Optional[Dict[str, Any]] = None
    is_published: Optional[bool] = None
    brand_id: Optional[int] = None
    series_id: Optional[int] = None
    tag_ids: Optional[List[int]] = None
    manuals: List[ProductManualPayload] = Field(default_factory=list)


class ProductCreate(BaseModel):
    title: str = Field(min_length=1)
    price: int = Field(default=0, ge=0)
    old_price: Optional[int] = None
    product_kind: ProductKind = "unknown"
    slug: Optional[str] = None
    description: str = ""
    is_inverter: bool = False
    power_cooling: Optional[float] = None
    main_image: Optional[str] = None
    source_url: Optional[str] = None
    specs: Dict[str, Any] = Field(default_factory=dict)
    is_published: bool = True
    brand_id: Optional[int] = None
    series_id: Optional[int] = None
    tag_ids: List[int] = Field(default_factory=list)
    manuals: List[ProductManualPayload] = Field(default_factory=list)


class ProductDuplicatePayload(ProductUpdate):
    copy_gallery: bool = True
    copy_manuals: bool = True
    copy_tags: bool = True
    make_unpublished: bool = False


class SupplierResponse(BaseModel):
    id: int
    name: str
    code: str
    is_active: bool
    priority: int
    spreadsheet_id: Optional[str] = None
    spreadsheet_url: Optional[str] = None
    google_sheet_synced_at: Optional[datetime] = None
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    legal_address: Optional[str] = None
    postal_address: Optional[str] = None
    default_payment_method: str = "unknown"
    payment_comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SupplierCreatePayload(BaseModel):
    name: str
    code: Optional[str] = None
    spreadsheet_id_or_url: Optional[str] = None
    is_active: bool = True
    priority: int = 100
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    legal_address: Optional[str] = None
    postal_address: Optional[str] = None
    default_payment_method: str = "unknown"
    payment_comment: Optional[str] = None


class SupplierUpdatePayload(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    spreadsheet_id_or_url: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    legal_name: Optional[str] = None
    tax_id: Optional[str] = None
    legal_address: Optional[str] = None
    postal_address: Optional[str] = None
    default_payment_method: Optional[str] = None
    payment_comment: Optional[str] = None


class SupplierListResponse(BaseModel):
    items: List[SupplierResponse]


class SupplierContactBasePayload(BaseModel):
    name: str
    role: Optional[str] = None
    phone: Optional[str] = None
    viber: Optional[str] = None
    telegram_username: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None
    preferred_channel: str = "phone"
    default_for_orders: bool = False
    default_for_logistics: bool = False
    comment: Optional[str] = None


class SupplierContactCreatePayload(SupplierContactBasePayload):
    pass


class SupplierContactUpdatePayload(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    viber: Optional[str] = None
    telegram_username: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None
    preferred_channel: Optional[str] = None
    default_for_orders: Optional[bool] = None
    default_for_logistics: Optional[bool] = None
    comment: Optional[str] = None


class SupplierContactResponse(SupplierContactBasePayload):
    id: int
    supplier_id: int
    created_at: datetime
    updated_at: datetime


class SupplierContactListResponse(BaseModel):
    items: List[SupplierContactResponse]


class SupplierWarehouseBasePayload(BaseModel):
    name: str
    address: str
    contact_id: Optional[int] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    work_hours: Optional[str] = None
    pickup_notes: Optional[str] = None
    is_default: bool = False


class SupplierWarehouseCreatePayload(SupplierWarehouseBasePayload):
    pass


class SupplierWarehouseUpdatePayload(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    contact_id: Optional[int] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    work_hours: Optional[str] = None
    pickup_notes: Optional[str] = None
    is_default: Optional[bool] = None


class SupplierWarehouseResponse(SupplierWarehouseBasePayload):
    id: int
    supplier_id: int
    created_at: datetime
    updated_at: datetime


class SupplierWarehouseListResponse(BaseModel):
    items: List[SupplierWarehouseResponse]


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
    col_source_url: Optional[str] = None
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
    col_source_url: Optional[str] = None
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
    col_source_url: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierPriceSourceListResponse(BaseModel):
    items: List[SupplierPriceSourceResponse]


class SupplierSourceAnalysisRow(BaseModel):
    row_number: int
    row_kind: str
    external_id: Optional[str] = None
    title_raw: Optional[str] = None
    source_url: Optional[str] = None
    model_tokens: List[str] = Field(default_factory=list)
    wholesale_raw: Optional[str] = None
    rrc_raw: Optional[str] = None
    qty_raw: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class SupplierSourceAnalysisResponse(BaseModel):
    source_id: int
    rows_total: int
    product_rows: int
    section_rows: int
    url_rows: int
    skipped_rows: int
    sample_rows: List[SupplierSourceAnalysisRow] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


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
    title_normalized: Optional[str] = None
    source_url: Optional[str] = None
    model_tokens: List[str] = Field(default_factory=list)
    indoor_model_tokens: List[str] = Field(default_factory=list)
    outdoor_model_tokens: List[str] = Field(default_factory=list)
    match_normalizer_version: Optional[str] = None
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


class SupplierSourceUrlImportCandidate(BaseModel):
    supplier_id: int
    supplier_name: Optional[str] = None
    source_id: Optional[int] = None
    source_name: Optional[str] = None
    external_id: str
    title_raw: Optional[str] = None
    source_url: str
    model_tokens: List[str] = Field(default_factory=list)
    qty: int = 0
    rrc_byn: Optional[float] = None


class SupplierSourceUrlImportCandidateListResponse(BaseModel):
    items: List[SupplierSourceUrlImportCandidate]
    total: int


class SupplierSourceUrlImportPayload(BaseModel):
    urls: List[str]
    with_related: bool = False
    update_existing: bool = False


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
    source_url: Optional[str] = None
    score: int = 0
    confidence: int = 0
    matched_tokens: List[str] = Field(default_factory=list)
    missing_tokens: List[str] = Field(default_factory=list)
    explanations: List[str] = Field(default_factory=list)
    score_breakdown: Dict[str, int] = Field(default_factory=dict)


class SupplierOfferSuggestionItem(BaseModel):
    supplier_id: int
    external_id: str
    normalized_query: str
    offer_tokens: List[str] = Field(default_factory=list)
    indoor_model_tokens: List[str] = Field(default_factory=list)
    outdoor_model_tokens: List[str] = Field(default_factory=list)
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


class SupplyRequestLineCreatePayload(BaseModel):
    source_type: str = "manual"
    order_product_link_id: Optional[int] = None
    product_id: Optional[int] = None
    supplier_offer_external_id: Optional[str] = None
    title: Optional[str] = None
    qty: int = 1
    unit_cost: Optional[float] = None
    reserved_until: Optional[datetime] = None
    comment: Optional[str] = None


class SupplyRequestCreatePayload(BaseModel):
    supplier_id: int
    warehouse_id: Optional[int] = None
    supplier_contact_id: Optional[int] = None
    logistics_contact_id: Optional[int] = None
    intent: str = "order"
    payment_method: Optional[str] = None
    comment: Optional[str] = None
    lines: List[SupplyRequestLineCreatePayload]


class SupplyRequestFromOrderLinesPayload(BaseModel):
    order_product_link_ids: List[int]
    intent: str = "order"
    supplier_id: Optional[int] = None
    warehouse_id: Optional[int] = None
    payment_method: Optional[str] = None
    comment: Optional[str] = None


class SupplyRequestStockLinePayload(BaseModel):
    supplier_id: int
    product_id: Optional[int] = None
    title: Optional[str] = None
    qty: int = 1
    warehouse_id: Optional[int] = None
    payment_method: Optional[str] = None
    supplier_offer_external_id: Optional[str] = None
    unit_cost: Optional[float] = None
    comment: Optional[str] = None


class SupplyRequestStockCreatePayload(BaseModel):
    intent: str = "order"
    comment: Optional[str] = None
    lines: List[SupplyRequestStockLinePayload]


class SupplyRequestUpdatePayload(BaseModel):
    warehouse_id: Optional[int] = None
    supplier_contact_id: Optional[int] = None
    logistics_contact_id: Optional[int] = None
    status: Optional[str] = None
    intent: Optional[str] = None
    payment_method: Optional[str] = None
    comment: Optional[str] = None


class SupplyRequestLineUpdatePayload(BaseModel):
    status: Optional[str] = None
    reserved_until: Optional[datetime] = None
    received_qty: Optional[int] = None
    comment: Optional[str] = None


class SupplyRequestLineResponse(BaseModel):
    id: int
    request_id: int
    order_product_link_id: Optional[int] = None
    source_type: str
    product_id: Optional[int] = None
    product_title: Optional[str] = None
    supplier_offer_external_id: Optional[str] = None
    supplier_offer_title: Optional[str] = None
    title_snapshot: str
    qty: int
    unit_cost_snapshot: Optional[float] = None
    status: str
    reserved_until: Optional[datetime] = None
    received_qty: int
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SupplyRequestResponse(BaseModel):
    id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    warehouse_id: Optional[int] = None
    warehouse_name: Optional[str] = None
    warehouse_address: Optional[str] = None
    supplier_contact_id: Optional[int] = None
    supplier_contact_name: Optional[str] = None
    logistics_contact_id: Optional[int] = None
    logistics_contact_name: Optional[str] = None
    status: str
    intent: str
    payment_method: str
    comment: Optional[str] = None
    supplier_message_snapshot: Optional[str] = None
    logistics_message_snapshot: Optional[str] = None
    created_by: Optional[str] = None
    supplier_message_sent_at: Optional[datetime] = None
    logistics_message_sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    lines: List[SupplyRequestLineResponse] = Field(default_factory=list)


class SupplyRequestListResponse(BaseModel):
    items: List[SupplyRequestResponse]
    meta: Meta


class SupplyRequestCreateResponse(BaseModel):
    items: List[SupplyRequestResponse]


class SupplyRequestMessagePayload(BaseModel):
    mark_sent: bool = False


class SupplyLogisticsMessagePayload(BaseModel):
    request_ids: List[int]
    mark_sent: bool = False


class SupplyMessageResponse(BaseModel):
    text: str
    request_ids: List[int] = Field(default_factory=list)


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
    attachment_count: int = 0


class LeadsInboxListResponse(BaseModel):
    items: List[LeadsInboxItemResponse]
    total: int
    meta: Meta


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


class MdvCatalogPreviewPayload(BaseModel):
    catalogs: List[str] = Field(default_factory=lambda: ["household", "semi", "multi"])
    sample_limit: int = Field(default=30, ge=1, le=100)
    replace_legacy_catalogs: List[str] = Field(default_factory=list)


class MdvCatalogImportPayload(BaseModel):
    catalogs: List[str] = Field(default_factory=lambda: ["household", "semi", "multi"])
    update_existing: bool = True
    replace_legacy_catalogs: List[str] = Field(default_factory=list)


class MdvCatalogPreviewItemResponse(BaseModel):
    catalog: str
    action: str
    title: str
    source_url: str
    existing_product_id: Optional[int] = None
    price_rub: int = 0
    series: str = ""
    type: str = ""
    model_indoor: str = ""
    model_outdoor: str = ""


class MdvCatalogSpecKeyStatResponse(BaseModel):
    key: str
    count: int


class MdvLegacyReplaceSampleResponse(BaseModel):
    product_id: Optional[int] = None
    title: str
    slug: str
    catalog: str
    action: str
    is_published: bool = True
    source_url: str = ""


class MdvLegacyReplacePreviewResponse(BaseModel):
    enabled: bool = False
    catalogs: List[str] = Field(default_factory=list)
    total: int = 0
    by_catalog: Dict[str, int] = Field(default_factory=dict)
    deletable_count: int = 0
    keep_for_update_count: int = 0
    deleted_count: int = 0
    archived_count: int = 0
    samples: List[MdvLegacyReplaceSampleResponse] = Field(default_factory=list)


class MdvCatalogPreviewResponse(BaseModel):
    catalogs: List[str]
    total: int
    by_catalog: Dict[str, int] = Field(default_factory=dict)
    actions: Dict[str, int] = Field(default_factory=dict)
    unmatched_source_urls: int = 0
    raw_spec_key_count: int = 0
    top_raw_spec_keys: List[MdvCatalogSpecKeyStatResponse] = Field(default_factory=list)
    top_unpromoted_spec_keys: List[MdvCatalogSpecKeyStatResponse] = Field(default_factory=list)
    samples: List[MdvCatalogPreviewItemResponse] = Field(default_factory=list)
    legacy_replace: MdvLegacyReplacePreviewResponse = Field(default_factory=MdvLegacyReplacePreviewResponse)
    source_urls: Dict[str, str] = Field(default_factory=dict)
    next_step: str = ""


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
    persistence_ok: bool
    persistence_error_code: Optional[str] = None


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
    pre_install = "pre_install"
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
    short_name: Optional[str] = None
    full_description: Optional[str] = None
    # Kept in the response while older Manager builds still consume them.
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
    short_name: str = Field(validation_alias=AliasChoices("short_name", "selector_label"))
    full_description: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("full_description", "estimate_template"),
    )
    category: str = ""
    power_range: str = ""
    base_price: int = 0
    included_route_meters: float = 3.0
    is_active: bool = True
    sort_order: int = 0
    comment: Optional[str] = None

    @field_validator("short_name")
    @classmethod
    def validate_short_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("short_name must not be empty")
        return value


class ManagerTariffUpdatePayload(BaseModel):
    service_kind: Optional[ManagerTariffServiceKind] = None
    short_name: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("short_name", "selector_label"),
    )
    full_description: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("full_description", "estimate_template"),
    )
    category: Optional[str] = None
    power_range: Optional[str] = None
    base_price: Optional[int] = None
    included_route_meters: Optional[float] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    comment: Optional[str] = None

    @field_validator("short_name")
    @classmethod
    def validate_optional_short_name(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("short_name must not be empty")
        return value


class ManagerTariffListResponse(BaseModel):
    items: List[ManagerTariffResponse]


class ManagerQuickTariffResponse(BaseModel):
    tariff_id: int
    service_kind: ManagerTariffServiceKind
    short_name: str
    full_description: Optional[str] = None
    # Compatibility title for Manager builds deployed before description modes.
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
    diagnostic_notes: Optional[str] = None
    refrigerant_type: Optional[str] = None
    refrigerant_amount: Optional[str] = None
    extra_context: Optional[str] = None
    current_meta: Dict[str, Any] = Field(default_factory=dict)


class ManagerRepairActAiDraftResponse(BaseModel):
    repair_meta: Dict[str, Any] = Field(default_factory=dict)
    provider: str = "deepseek"
    model: str
    prompt_version: str = "defect_act_v3"


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
    short_name: str
    full_description: Optional[str] = None
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
    short_name: Optional[str] = None
    full_description: Optional[str] = None
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


class ManagerServiceDescriptionMode(str, Enum):
    short = "short"
    full = "full"


class ManagerServiceEstimateOrderLinesResponse(BaseModel):
    estimate_id: int
    mode: ManagerServiceEstimateOrderLinesMode
    description_mode: ManagerServiceDescriptionMode
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
    allocated_amount: float = 0.0
    unallocated_amount: float = 0.0
    allocation_count: int = 0
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


class BankReceiptGroupAttachPayload(BaseModel):
    order_ids: List[int] = Field(default_factory=list)
    payment_type: str = "postpayment"


class BankReceiptAllocationPayload(BaseModel):
    order_id: int
    amount: float = Field(gt=0)


class BankReceiptAllocationsReplacePayload(BaseModel):
    allocations: List[BankReceiptAllocationPayload] = Field(default_factory=list)
    payment_type: str = "postpayment"


class BankReceiptAllocationOrderResponse(BaseModel):
    order_id: int
    title: Optional[str] = None
    customer_name: Optional[str] = None
    status: str
    created_at: datetime
    total_amount: float
    total_payments: float
    balance_due_before_receipt: float
    current_allocation: float
    resulting_balance_due: float


class BankReceiptAllocationDetailResponse(BaseModel):
    receipt_id: int
    status: str
    currency: PaymentCurrency
    receipt_amount: float
    allocated_amount: float
    unallocated_amount: float
    orders: List[BankReceiptAllocationOrderResponse] = Field(default_factory=list)


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


class OrderEmailComposePayload(BaseModel):
    document_ids: List[int] = Field(default_factory=list)
    template_key: str = "auto"


class OrderEmailTemplateOptionResponse(BaseModel):
    key: str
    label: str
    requires_documents: bool = True


class OrderEmailMissingRequisiteResponse(BaseModel):
    key: str
    label: str


class OrderEmailComposeResponse(BaseModel):
    template_key: str
    template_options: List[OrderEmailTemplateOptionResponse] = Field(default_factory=list)
    subject: str
    body_text: str
    document_ids: List[int] = Field(default_factory=list)
    document_labels: List[str] = Field(default_factory=list)
    missing_requisites: List[OrderEmailMissingRequisiteResponse] = Field(default_factory=list)


class OutgoingEmailAttachmentResponse(BaseModel):
    filename: Optional[str] = None
    mime_type: Optional[str] = None
    size: Optional[int] = None
    storage_key: Optional[str] = None
    document_id: Optional[int] = None
    document_type: Optional[str] = None
    document_number: Optional[str] = None


class OutgoingEmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    retry_of_email_id: Optional[int] = None
    order_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    order_title: Optional[str] = None
    recipient_email: str
    subject: str
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    attachments: Optional[List[OutgoingEmailAttachmentResponse]] = None
    error: Optional[str] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class OutgoingEmailDetailResponse(OutgoingEmailResponse):
    retry_attempts: List[OutgoingEmailResponse] = Field(default_factory=list)


class OutgoingEmailListResponse(BaseModel):
    items: List[OutgoingEmailResponse]
    total: int
    page: int
    limit: int
