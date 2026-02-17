from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

# --- SHARED ---

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
    tags: List[TagResponse] = []
    specs: Dict[str, Any] = {}
    images: List[str] = [] # Legacy
    gallery_images: List[ProductImageResponse] = [] # New
    series_siblings: List[ProductSiblingResponse] = []

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

class OrderPayload(BaseModel):
    customer: CustomerPayload
    items: List[CartItemPayload] = []
    comment: Optional[str] = None

class OrderResponse(BaseModel):
    id: int
    status: str
    total_amount: float
    created_at: datetime


class OrderCustomerBrief(BaseModel):
    id: int
    type: str
    name: str
    phone: str
    full_legal_name: Optional[str] = None
    inn: Optional[str] = None


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
    created_at: datetime
    updated_at: Optional[datetime] = None
    next_followup_date: Optional[datetime] = None
    assessment_date: Optional[datetime] = None
    installation_date: Optional[datetime] = None
    total_amount: float
    total_cost: float
    margin: float
    is_paid: bool
    comment: Optional[str] = None
    delivery_address: Optional[str] = None
    customer: Optional[OrderCustomerBrief] = None


class ManagerOrderDetailResponse(ManagerOrderListItemResponse):
    product_lines: List[OrderProductLineResponse] = []
    service_lines: List[OrderServiceLineResponse] = []


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
    assessment_date: Optional[datetime] = None
    installation_date: Optional[datetime] = None
    comment: Optional[str] = None
    is_paid: Optional[bool] = None
    products: Optional[List[ManagerOrderProductLinePayload]] = None
    services: Optional[List[ManagerOrderServiceLinePayload]] = None


class ManagerOrderDocumentResponse(BaseModel):
    doc_id: int
    doc_type: str
    edit_url: str


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


class LeadQualifyPayload(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    full_legal_name: Optional[str] = None
    delivery_address: Optional[str] = None
    customer_type: Optional[str] = None
    order_comment: Optional[str] = None


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


class ManagerCatalogProductTagResponse(BaseModel):
    id: int
    title: str
    slug: str
    group_title: Optional[str]
    group_color: Optional[str]


class ManagerCatalogProductItemResponse(BaseModel):
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
    specs: Dict[str, Any]
    gallery_images: List[ManagerCatalogProductImageResponse]
    tags: List[ManagerCatalogProductTagResponse]


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
    full_legal_name: Optional[str]
    created_at: Optional[datetime]
    order_count: int


class ManagerCatalogCustomerListResponse(BaseModel):
    items: List[ManagerCatalogCustomerItemResponse]
    meta: Meta


class ManagerTagOptionResponse(BaseModel):
    id: int
    title: str
    slug: str


class ManagerTagGroupResponse(BaseModel):
    id: int
    title: str
    slug: str
    color: str
    allow_multiple: bool
    tags: List[ManagerTagOptionResponse]


class ManagerActionMessageResponse(BaseModel):
    message: str


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
    tag_ids: Optional[List[int]] = None


class BulkRoundRequest(BaseModel):
    product_ids: List[int]
