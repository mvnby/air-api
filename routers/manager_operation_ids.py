"""Stable operationId constants for manager API routes."""

READ_USER_ME = "read_user_me"
GET_MANAGER_CALENDAR_EVENTS = "get_manager_calendar_events"

GET_MANAGER_PRODUCTS = "get_manager_products"
GET_MANAGER_CUSTOMERS = "get_manager_customers"
GET_MANAGER_CUSTOMER_DETAIL = "get_manager_customer_detail"
GET_MANAGER_CUSTOMER_DOCS = "get_manager_customer_docs"
PATCH_MANAGER_CUSTOMER = "patch_manager_customer"
UPDATE_PRODUCT = "update_product"
BULK_ROUND_PRICE = "bulk_round_price"
GET_ALL_TAGS = "get_all_tags"
SMART_SEARCH_PRODUCTS = "smart_search_products"

BULK_UPDATE_SPECS = "bulk_update_specs"
NORMALIZE_LEGACY_SPECS = "normalize_legacy_specs"

SEARCH_IMAGES = "search_images"
UPLOAD_IMAGE = "upload_image"
UPLOAD_LOCAL_IMAGES = "upload_local_images"

REUSE_SEARCH = "reuse_search"
GET_COMMON_GALLERY_IMAGES = "get_common_gallery_images"
LINK_SEARCH_RESULT = "link_search_result"
SET_MAIN_IMAGE = "set_main_image"
DELETE_IMAGE = "delete_image"
REUSE_IMAGE = "reuse_image"
BULK_ADD_GALLERY_IMAGES = "bulk_add_gallery_images"
BULK_UPLOAD_LOCAL_IMAGES = "bulk_upload_local_images"
BULK_DELETE_COMMON_GALLERY_IMAGES = "bulk_delete_common_gallery_images"
CLEANUP_MEDIA = "cleanup_media"

GET_MANAGER_LEADS = "get_manager_leads"
CREATE_MANAGER_LEAD = "create_manager_lead"
PATCH_MANAGER_LEAD = "patch_manager_lead"
QUALIFY_MANAGER_LEAD = "qualify_manager_lead"
MARK_MANAGER_LEAD_LOST = "mark_manager_lead_lost"

GET_MANAGER_ORDERS = "get_manager_orders"
GET_MANAGER_ORDER_DETAIL = "get_manager_order_detail"
PATCH_MANAGER_ORDER = "patch_manager_order"
GENERATE_MANAGER_ORDER_DOCUMENT = "generate_manager_order_document"
GET_MANAGER_ORDER_DOCUMENTS = "get_manager_order_documents"
GET_MANAGER_DOC_DOWNLOAD = "get_manager_doc_download"
DELETE_MANAGER_DOC = "delete_manager_doc"
GET_MANAGER_CRM_HEALTH_REPORT = "get_manager_crm_health_report"
GET_DASHBOARD_STATS = "get_dashboard_stats"
IMPORT_ONLINER = "import_onliner"

GET_MANAGER_INSTALLERS = "get_manager_installers"
CREATE_MANAGER_INSTALLER = "create_manager_installer"
UPDATE_MANAGER_INSTALLER = "update_manager_installer"
SEARCH_MANAGER_INSTALLERS = "search_manager_installers"


ALL_MANAGER_OPERATION_IDS = (
    READ_USER_ME,
    GET_MANAGER_CALENDAR_EVENTS,
    GET_MANAGER_PRODUCTS,
    GET_MANAGER_CUSTOMERS,
    GET_MANAGER_CUSTOMER_DETAIL,
    GET_MANAGER_CUSTOMER_DOCS,
    PATCH_MANAGER_CUSTOMER,
    UPDATE_PRODUCT,
    BULK_ROUND_PRICE,
    GET_ALL_TAGS,
    SMART_SEARCH_PRODUCTS,
    BULK_UPDATE_SPECS,
    NORMALIZE_LEGACY_SPECS,
    SEARCH_IMAGES,
    UPLOAD_IMAGE,
    UPLOAD_LOCAL_IMAGES,
    REUSE_SEARCH,
    GET_COMMON_GALLERY_IMAGES,
    LINK_SEARCH_RESULT,
    SET_MAIN_IMAGE,
    DELETE_IMAGE,
    REUSE_IMAGE,
    BULK_ADD_GALLERY_IMAGES,
    BULK_UPLOAD_LOCAL_IMAGES,
    BULK_DELETE_COMMON_GALLERY_IMAGES,
    CLEANUP_MEDIA,
    GET_MANAGER_LEADS,
    CREATE_MANAGER_LEAD,
    PATCH_MANAGER_LEAD,
    QUALIFY_MANAGER_LEAD,
    MARK_MANAGER_LEAD_LOST,
    GET_MANAGER_ORDERS,
    GET_MANAGER_ORDER_DETAIL,
    PATCH_MANAGER_ORDER,
    GENERATE_MANAGER_ORDER_DOCUMENT,
    GET_MANAGER_ORDER_DOCUMENTS,
    GET_MANAGER_DOC_DOWNLOAD,
    DELETE_MANAGER_DOC,
    GET_MANAGER_CRM_HEALTH_REPORT,
    GET_DASHBOARD_STATS,
    IMPORT_ONLINER,
    GET_MANAGER_INSTALLERS,
    CREATE_MANAGER_INSTALLER,
    UPDATE_MANAGER_INSTALLER,
    SEARCH_MANAGER_INSTALLERS,
)
