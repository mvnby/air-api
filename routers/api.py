"""
API Router: Product endpoints.
Uses Service Layer with Dependency Injection for session management.
"""
from fastapi import APIRouter, Depends, Query
from core.security import get_current_username
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from typing import List, Optional
import logging

from core.database import get_session
from services.product_service import ProductService
from services.product_serialization import sanitize_specs, parse_legacy_images
from routers.api_admin import router as admin_router
from routers.api_content import router as content_router
from routers.api_proxy import router as proxy_router
from models import Product
from services.description_generator import DescriptionGeneratorService
from schemas import (
    CatalogResponse,
    Meta,
    ProductResponse,
    ProductSiblingResponse,
    ProductPriceResponse,
    OrderPayload,
    OrderResponse,
    TagResponse,
    TagGroupResponse,
    ProductImageResponse,
    SpecsKeysResponse,
    FiltersConfigResponse,
)
from crud.product import ProductDAO
from models import Order, Customer, OrderStatus, OrderProductLink, CustomerType
from fastapi import HTTPException

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(admin_router)
router.include_router(content_router)
router.include_router(proxy_router)
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---

def _map_product_to_response(
    product: Product,
    series_siblings: Optional[List[Product]] = None,
) -> ProductResponse:
    """Convert Product model to ProductResponse schema."""
    p_tags = []
    # Ensure tags are loaded
    if product.tags:
        for t in product.tags:
            g_resp = None
            if t.group:
                g_resp = TagGroupResponse(
                    title=t.group.title,
                    slug=t.group.slug,
                    is_public=t.group.is_public
                )
            
            p_tags.append(TagResponse(
                id=t.id, 
                title=t.title, 
                slug=t.slug, 
                is_public=t.is_public,
                sort_order=t.sort_order,
                group=g_resp,
                group_title=t.group.title if t.group else None
            ))
    
    specs = sanitize_specs(product.specs)
    images = parse_legacy_images(product.images)

            
    # Map gallery images
    gallery = []
    if product.gallery_images:
        for img in product.gallery_images:
            gallery.append(ProductImageResponse(
                id=img.id,
                url=img.url,
                is_installation_photo=img.is_installation_photo,
            ))

    siblings_payload = [
        ProductSiblingResponse(
            id=item.id,
            title=item.title,
            slug=item.slug,
            price=item.price,
            old_price=item.old_price,
            area=item.area,
            is_inverter=item.is_inverter,
            main_image=item.main_image,
        )
        for item in (series_siblings or [])
    ]

    return ProductResponse(
        id=product.id,
        title=product.title,
        slug=product.slug,
        price=product.price,
        old_price=product.old_price,
        area=product.area,
        is_inverter=product.is_inverter,
        power_cooling=product.power_cooling,
        main_image=product.main_image,
        is_published=product.is_published,
        created_at=product.created_at,
        tags=p_tags,
        specs=specs or {},
        images=images or [],
        gallery_images=gallery,
        series_siblings=siblings_payload,
    )

def _validate_pagination(page: int, limit: int) -> None:
    """Validate pagination parameters."""
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 1000")


# Legacy endpoints /products and /products/{id} removed in favor of /v1/products


@router.get("/v1/specs/keys", response_model=SpecsKeysResponse, operation_id="get_public_spec_keys")
async def get_public_spec_keys(
    session: AsyncSession = Depends(get_session)
):
    """
    Публичный список всех доступных характеристик.
    Используется для построения динамических фильтров на сайте.
    """
    # Логика та же самая, но доступ открыт всем
    stmt = select(Product.specs)
    result = await session.execute(stmt)
    all_specs = result.scalars().all()
    
    stats = {}
    for spec_dict in all_specs:
        if spec_dict:
            for key in spec_dict.keys():
                if str(key).startswith("__"):
                    continue
                stats[key] = stats.get(key, 0) + 1
            
    sorted_keys = sorted(stats.keys())
    return SpecsKeysResponse(keys=sorted_keys, total_products_using=stats)


@router.get("/v1/filters/config", response_model=FiltersConfigResponse, operation_id="get_filters_config")
async def get_filters_config(session: AsyncSession = Depends(get_session)):
    """Return filter configuration for storefront controls."""
    return await ProductService.get_filters_config(session)

@router.post("/products/{product_id}/generate-description")
async def generate_product_description(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Генерирует описание на основе тегов и возвращает текст.
    Админ может потом его отредактировать и сохранить.
    """
    text = await DescriptionGeneratorService.generate(session, product_id)
    return {"description": text}

# --- V1 HEADLESS COMMERCE API ---

@router.get("/v1/catalog", response_model=CatalogResponse, operation_id="get_products")
@router.get("/v1/products", response_model=CatalogResponse, operation_id="get_products_v1")
async def get_catalog(
    page: int = 1,
    limit: int = 20,
    sort: str = "newest",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    area_min: Optional[int] = None,
    area_max: Optional[int] = None,
    heating_min: Optional[int] = None,
    has_wifi: Optional[bool] = None,
    tag_slugs: Optional[List[str]] = Query(None),
    is_inverter: Optional[bool] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Get paginated product catalog with filtering and sorting.
    
    **Filters:**
    - `min_price`, `max_price`: Price range filter
    - `area_min`, `area_max`: Area coverage filter
    - `heating_min`: Min outdoor heating temperature support (e.g. -25)
    - `has_wifi`: Wi-Fi availability
    - `tag_slugs`: Filter by tag slugs for brand/series/expert-badge groups
    - `is_inverter`: Filter by inverter technology
    
    **Sorting:**
    - `newest`: Recently added products (default)
    - `price_asc`: Price low to high
    - `price_desc`: Price high to low
    - `area_asc`: Area low to high
    - `area_desc`: Area high to low
    """
    _validate_pagination(page, limit)
    
    # Resolve tags for faceted filtering if provided
    faceted_tag_ids = None
    if tag_slugs:
        faceted_tag_ids = await ProductService.resolve_slugs_to_grouped_ids(session, tag_slugs)
    
    items = await ProductDAO.get_filtered(
        session,
        area_min=area_min,
        area_max=area_max,
        min_price=min_price,
        max_price=max_price,
        heating_min=heating_min,
        has_wifi=has_wifi,
        is_inverter=is_inverter,
        # We pass None for tag_slugs because we handle it via faceted_tag_ids now
        tag_slugs=None, 
        faceted_tag_ids=faceted_tag_ids,
        sort=sort,
        page=page,
        limit=limit,
        is_published=True
    )
    total = await ProductDAO.count_filtered(
        session,
        area_min=area_min,
        area_max=area_max,
        min_price=min_price,
        max_price=max_price,
        heating_min=heating_min,
        has_wifi=has_wifi,
        is_inverter=is_inverter,
        tag_slugs=None,
        faceted_tag_ids=faceted_tag_ids,
        is_published=True
    )
    
    mapped_items = [_map_product_to_response(p) for p in items]
    pages = (total + limit - 1) // limit if limit > 0 else 0
    
    return CatalogResponse(
        items=mapped_items,
        meta=Meta(total=total, page=page, limit=limit, pages=pages)
    )

@router.get("/v1/products/{identifier}", response_model=ProductResponse, operation_id="get_product")
async def get_product_by_identifier(identifier: str, session: AsyncSession = Depends(get_session)):
    """
    Get product details by ID or slug (Hybrid Access).
    
    Returns full product information including tags, specifications, and images.
    Raises 404 if product not found.
    """
    product = await ProductService.get_product_by_identifier(session, identifier)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product with identifier '{identifier}' not found")
    siblings = await ProductService.get_series_siblings(session, product, limit=8)
    return _map_product_to_response(product, series_siblings=siblings)

# --- ORDER ENDPOINTS ---

@router.post("/v1/orders", response_model=OrderResponse, operation_id="create_order")
async def create_order(payload: OrderPayload, session: AsyncSession = Depends(get_session)):
    """
    Create a new order from website.
    
    Accepts customer information and cart items. Creates or updates customer record,
    creates order with NEW_LEAD status and lead_source=SITE.
    
    Returns created order details.
    """
    from services.order_service import OrderService
    from models import LeadSource
    
    # DEBUG: Log incoming payload
    logger.info(f"📦 Incoming order payload: customer={payload.customer.name}, items_count={len(payload.items)}")
    for idx, item in enumerate(payload.items):
        logger.info(f"   Item {idx}: product_id={item.product_id}, qty={item.quantity}, with_install={getattr(item, 'with_installation', 'N/A')}, install_price={getattr(item, 'installation_price', 'N/A')}")
    
    # If items provided, convert them
    items = [{
        "product_id": item.product_id, 
        "quantity": item.quantity,
        "with_installation": item.with_installation,
        "installation_price": item.installation_price,
        "installation_meta": item.installation_meta,
        "installation_options": item.installation_options
    } for item in payload.items]
    
    # Delegate to OrderService with SITE lead source
    order = await OrderService.create_from_website(
        session=session,
        customer_name=payload.customer.name,
        customer_phone=payload.customer.phone,
        customer_email=payload.customer.email,
        customer_address=payload.customer.address,
        items=items,
        lead_source=LeadSource.SITE,
        comment=payload.comment,
        customer_type=payload.customer.type,
        customer_inn=payload.customer.inn,
        customer_legal_name=payload.customer.full_legal_name,
        customer_legal_address=payload.customer.legal_address,
        customer_iban=payload.customer.iban,
        customer_bic=payload.customer.bic,
        customer_bank_name=payload.customer.bank_name
    )
    
    # Отправляем уведомление админам в Telegram
    from core.config import settings
    from services.bot_service import BotService
    
    if settings.admin_list:
        # Подгружаем связи для уведомления
        # Подгружаем связи для уведомления
        await session.refresh(order, ["product_links", "service_links", "customer"])
        for link in order.product_links:
            await session.refresh(link, ["product"])
        
        # Формируем сообщение
        message_lines = [
            f"🌐 <b>ЗАКАЗ С САЙТА #{order.id}</b>",
            f"👤 {payload.customer.name}",
            f"📱 {payload.customer.phone}",
        ]
        
        if payload.customer.email:
            message_lines.append(f"📧 {payload.customer.email}")
        if payload.customer.address:
            message_lines.append(f"📍 {payload.customer.address}")
        if payload.comment:
            message_lines.append(f"💬 {payload.comment}")
            
        message_lines.append("")
        message_lines.append("🛒 <b>Товары:</b>")
        
        for link in order.product_links:

            product_name = link.product.title if link.product else f"Product #{link.product_id}"
            line_total = link.price * link.quantity
            product_line = f"▫️ {product_name} x{link.quantity} — {line_total} р."
            message_lines.append(product_line)
            
            # Добавляем строку монтажа если включен
            if link.is_installation_included:
                install_price = link.installation_price or 0
                install_line = f"   └ 🔧 Монтаж: {install_price} BYN"
                message_lines.append(install_line)
        
        # Добавляем услуги (включая Standalone монтаж)
        if order.service_links:
            for s_link in order.service_links:
                 title = s_link.title or "Услуга"
                 total = s_link.price * s_link.quantity
                 message_lines.append(f"🔧 {title} x{s_link.quantity} — {total} BYN")
        
        message_lines.append("")
        message_lines.append(f"💰 <b>Итого: {order.total_amount} руб.</b>")
        
        admin_text = "\n".join(message_lines)
        
        for admin_id in settings.admin_list:
            try:
                await BotService.send_message(admin_id, admin_text)
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")
    
    return OrderResponse(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        created_at=order.created_at
    )
