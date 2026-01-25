"""
API Router: Product endpoints.
Uses Service Layer with Dependency Injection for session management.
"""
from fastapi import APIRouter, Depends, Query
from core.security import get_current_username
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select, and_, func
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from core.database import get_session
from services.product_service import ProductService
from models import Product, Tag, TagGroup, ProductTagLink
from services.description_generator import DescriptionGeneratorService
import httpx
from schemas import (
    CatalogResponse,
    Meta,
    ProductResponse,
    ArticleResponse,
    ServiceResponse,
    OrderPayload,
    OrderResponse,
    TagResponse,
    TagGroupResponse
)
from crud.product import ProductDAO
from models import Article, Service, Order, Customer, OrderStatus, OrderProductLink, CustomerType
from fastapi import HTTPException

router = APIRouter(prefix="/api", tags=["api"])
logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---

def _map_product_to_response(product: Product) -> ProductResponse:
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
                group=g_resp,
                group_title=t.group.title if t.group else None
            ))
    
    # Handle potentially string-encoded JSON fields
    import json
    specs = product.specs
    if isinstance(specs, str):
        try:
            # Replace single quotes with double quotes for valid JSON if needed, 
            # but usually it's better to try literal_eval if it's a python repr
            import ast
            specs = ast.literal_eval(specs)
        except Exception:
            specs = {}  # Fallback if JSON parsing fails
            
    images = product.images
    if isinstance(images, str):
        try:
            import ast
            images = ast.literal_eval(images)
        except Exception:
            images = []  # Fallback if JSON parsing fails

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
        images=images or []
    )

def _validate_pagination(page: int, limit: int) -> None:
    """Validate pagination parameters."""
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")


@router.get("/products")
async def get_products(session: AsyncSession = Depends(get_session)):
    """Get all published products."""
    products = await ProductService.get_all(session)
    return {"items": products}


@router.get("/products/{product_id}")
async def get_product(product_id: int, session: AsyncSession = Depends(get_session)):
    """Get a single product by ID."""
    product = await ProductService.get_by_id(session, product_id)
    return product


@router.get("/products/search")
async def search_products(
    q: str = None,
    is_inverter: bool = None,
    session: AsyncSession = Depends(get_session)
):
    """Search products with fuzzy matching."""
    products = await ProductService.search(session, query=q, is_inverter=is_inverter)
    return {"items": products}

@router.get("/admin/tags/filterable")
async def get_filterable_tags(
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    stmt = (
        select(TagGroup, Tag)
        .join(Tag, Tag.group_id == TagGroup.id)
        .where(Tag.is_filter == True)
        .order_by(TagGroup.sort_order, TagGroup.title, Tag.sort_order, Tag.title)
    )
    result = await session.execute(stmt)
    
    grouped = {}
    for row in result:
        group, tag = row
        if group.title not in grouped:
            grouped[group.title] = {
                "group_label": group.title,
                "tags": []
            }
        grouped[group.title]["tags"].append({
            "id": tag.id,
            "title": tag.title,
            "slug": tag.slug
        })
    
    return list(grouped.values())

# ADMIN SEARCH ENDPOINTS (for Select2)
@router.get("/admin/products/search")
async def admin_search_products(
    q: str = "", 
    tag_ids: List[int] = Query(None),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    stmt = select(Product)
    
    # 1. Фильтрация по тегам (AND логика)
    if tag_ids:
        # Для AND логики: продукт должен иметь связь со ВСЕМИ указанными тегами
        tag_subquery = (
            select(ProductTagLink.product_id)
            .where(ProductTagLink.tag_id.in_(tag_ids))
            .group_by(ProductTagLink.product_id)
            .having(func.count(ProductTagLink.tag_id) == len(tag_ids))
        )
        stmt = stmt.where(Product.id.in_(tag_subquery))
    
    # 2. Поиск по тексту (в названии или описании)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            (Product.title.ilike(pattern)) | (Product.description.ilike(pattern))
        )
    
    stmt = stmt.limit(20)
    result = await session.execute(stmt)
    products = result.scalars().all()
    return [{"id": p.id, "text": p.title, "price": p.price} for p in products]

@router.get("/admin/services/search")
async def admin_search_services(
    q: str = "",
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    from models import Service
    stmt = select(Service).where(Service.title.ilike(f"%{q}%")).limit(20)
    result = await session.execute(stmt)
    services = result.scalars().all()
    return [{"id": s.id, "text": s.title, "price": s.base_price} for s in services]


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_session)):
    """Check API and database availability."""
    try:
        await session.execute(select(1))
        return {"status": "ok", "database": "online"}
    except Exception as e:
        return {"status": "error", "database": "offline", "detail": str(e)}

# --- BELARUS API PROXIES ---

@router.get("/admin/proxy/egr")
async def proxy_egr(
    unp: str,
    username: str = Depends(get_current_username)
):
    """Proxy for Belarus EGR (Ministry of Taxes) API."""
    url = f"http://grp.nalog.gov.by/api/grp-public/data?unp={unp}&type=json&charset=UTF-8"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            return response.json()
        except Exception as e:
            return {"error": str(e)}
# Простой кэш в памяти, чтобы не долбить НБРБ при каждом клике
# (В идеале можно использовать Redis, но для справочника банков это оверхед)
BANK_CACHE = {
    "data": [],
    "last_updated": None
}

async def get_all_banks():
    """Получает список банков с кэшированием на 72 часа"""
    now = datetime.now()
    if BANK_CACHE["data"] and BANK_CACHE["last_updated"]:
        if now - BANK_CACHE["last_updated"] < timedelta(hours=72):
            return BANK_CACHE["data"]
            
    url = "https://api.nbrb.by/bic"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                BANK_CACHE["data"] = data
                BANK_CACHE["last_updated"] = now
                return data
        except Exception as e:
            logger.error(f"Error fetching banks: {e}")
            # Если ошибка сети, пробуем вернуть старый кэш
            return BANK_CACHE["data"]
    return []

@router.get("/admin/proxy/bank")
async def find_bank(
    search: str = Query(None, description="BIC код или IBAN"),
    username: str = Depends(get_current_username)
):
    """
    Ищет банк локально в справочнике НБРБ.
    Принимает:
    - BIC (код банка, например '153001755')
    - IBAN (вырезает код из строки вида BYxx [CODE] xxxx...)
    """
    
    # 1. Нормализация запроса
    if not search:
        return await get_all_banks()

    query = search.strip().replace(" ", "").upper()
    target_bic = query

    # 2. Если это IBAN (Беларусь = 28 символов, начинается на BY), вырезаем код
    # Формат: BYxx [BICK] ... (символы с 5 по 8 - это код банка буквенный, но в API НБРБ коды цифровые)
    # НО! В API НБРБ есть поле 'CdBic' (буквенный) и 'CdBank' (цифровой).
    
    # Если пользователь ввел короткий код (БИК)
    banks = await get_all_banks()
    
    found_bank = None
    
    # Пытаемся найти по полному совпадению CDBank (SWIFT/BIC код вида OLMPBY2X) 
    # или по префиксу банка из IBAN (символы 4-8, например 'OLMP' для Белгазпромбанка)
    
    bic_from_iban = None
    if len(query) >= 8 and query.startswith("BY"):
         bic_from_iban = query[4:8] # Вырезаем 4-буквенный код банка из IBAN
    
    for bank in banks:
        # Данные в JSON НБРБ выглядят так:
        # {"CDBank": "OLMPBY2X", "NmBankShort": "ОАО 'Белгазпромбанк'", "DtEnd": null, ...}
        # CDBank - это SWIFT/BIC код банка (8-11 символов)
        # DtEnd = null означает текущую (активную) запись
        
        cd_bank = bank.get("CDBank", "")
        is_active = bank.get("DtEnd") is None
        
        # 1. Проверка по полному SWIFT/BIC коду (если ввели полный код, например "OLMPBY2X")
        if cd_bank == target_bic:
            # Если нашли активный банк - сразу возвращаем
            if is_active:
                found_bank = bank
                break
            # Иначе сохраняем как fallback
            elif not found_bank:
                found_bank = bank
            
        # 2. Проверка по 4-буквенному коду из IBAN (первые 4 символа CDBank)
        if bic_from_iban and cd_bank.startswith(bic_from_iban):
            # Если нашли активный банк - сразу возвращаем
            if is_active:
                found_bank = bank
                break
            # Иначе сохраняем как fallback
            elif not found_bank:
                found_bank = bank

    if found_bank:
        return {
            "name": found_bank.get("NmBankShort"),
            "address": found_bank.get("AdrBank"),
            "bic": found_bank.get("CDBank"),     # SWIFT/BIC код
            "swift": found_bank.get("CDBank")    # То же самое
        }
    
    return {"error": "Банк не найден", "debug_bic": bic_from_iban or target_bic}

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

@router.get("/v1/catalog", response_model=CatalogResponse)
async def get_catalog(
    page: int = 1,
    limit: int = 20,
    sort: str = "newest",
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    area_min: Optional[int] = None,
    area_max: Optional[int] = None,
    tag_slugs: Optional[List[str]] = Query(None),
    is_inverter: Optional[bool] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    Get paginated product catalog with filtering and sorting.
    
    **Filters:**
    - `min_price`, `max_price`: Price range filter
    - `area_min`, `area_max`: Area coverage filter
    - `tag_slugs`: Filter by tag slugs (e.g., 'inverter', 'chigo', 'area-25')
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

@router.get("/v1/products/{slug}", response_model=ProductResponse)
async def get_product_by_slug(slug: str, session: AsyncSession = Depends(get_session)):
    """
    Get product details by slug.
    
    Returns full product information including tags, specifications, and images.
    Raises 404 if product not found.
    """
    product = await ProductDAO.get_by_slug(session, slug)
    if not product:
        raise HTTPException(status_code=404, detail=f"Product with slug '{slug}' not found")
    
    return _map_product_to_response(product)

# --- CONTENT ENDPOINTS ---

@router.get("/v1/content/articles", response_model=List[ArticleResponse])
async def get_articles(session: AsyncSession = Depends(get_session)):
    """Get list of published articles ordered by creation date (newest first)."""
    from services.article_service import ArticleService
    return await ArticleService.get_all_published(session)

@router.get("/v1/content/articles/{slug}", response_model=ArticleResponse)
async def get_article(slug: str, session: AsyncSession = Depends(get_session)):
    """Get article details by slug. Returns 404 if not found or not published."""
    from services.article_service import ArticleService
    article = await ArticleService.get_by_slug(session, slug)
    if not article:
        raise HTTPException(status_code=404, detail=f"Article with slug '{slug}' not found")
    return article

@router.get("/v1/content/services", response_model=List[ServiceResponse])
async def get_services(session: AsyncSession = Depends(get_session)):
    """Get list of all available services."""
    stmt = select(Service).order_by(Service.id)
    result = await session.execute(stmt)
    return result.scalars().all()

@router.get("/v1/installation-rates")
async def get_installation_rates(session: AsyncSession = Depends(get_session)):
    """Get all installation rates."""
    from services.installation_service import InstallationService
    return await InstallationService.get_all(session)

# --- ORDER ENDPOINTS ---

@router.post("/v1/orders", response_model=OrderResponse)
async def create_order(payload: OrderPayload, session: AsyncSession = Depends(get_session)):
    """
    Create a new order from website.
    
    Accepts customer information and cart items. Creates or updates customer record,
    creates order with NEW_LEAD status and lead_source=SITE.
    
    Returns created order details.
    """
    from services.order_service import OrderService
    from models import LeadSource
    
    # If items provided, convert them
    items = [{"product_id": item.product_id, "quantity": item.quantity} for item in payload.items]
    
    # Delegate to OrderService with SITE lead source
    order = await OrderService.create_from_website(
        session=session,
        customer_name=payload.customer.name,
        customer_phone=payload.customer.phone,
        customer_email=payload.customer.email,
        customer_address=payload.customer.address,
        items=items,
        lead_source=LeadSource.SITE,
        comment=payload.comment
    )
    
    return OrderResponse(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        created_at=order.created_at
    )

# --- CONFIG ENDPOINTS ---

@router.get("/v1/config")
async def get_global_config(session: AsyncSession = Depends(get_session)):
    """
    Get all global configuration parameters as a key-value dictionary.
    Example: {"phone": "+37529...", "email": "..."}
    """
    from models import GlobalConfig
    stmt = select(GlobalConfig)
    result = await session.execute(stmt)
    configs = result.scalars().all()
    
    # Convert list of configs to simple key-value dict
    return {c.key: c.value for c in configs}