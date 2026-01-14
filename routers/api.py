"""
API Router: Product endpoints.
Uses Service Layer with Dependency Injection for session management.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select, and_, func
from typing import List, Optional
from datetime import datetime, timedelta

from core.database import get_session
from services.product_service import ProductService
from models import Product, Tag, TagGroup, ProductTagLink
from services.description_generator import DescriptionGeneratorService
import httpx

router = APIRouter(prefix="/api", tags=["api"])


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
async def get_filterable_tags(session: AsyncSession = Depends(get_session)):
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
    session: AsyncSession = Depends(get_session)
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
async def admin_search_services(q: str = "", session: AsyncSession = Depends(get_session)):
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
async def proxy_egr(unp: str):
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
    """Получает список банков с кэшированием на 1 час"""
    now = datetime.now()
    if BANK_CACHE["data"] and BANK_CACHE["last_updated"]:
        if now - BANK_CACHE["last_updated"] < timedelta(hours=1):
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
            print(f"Error fetching banks: {e}")
            # Если ошибка сети, пробуем вернуть старый кэш
            return BANK_CACHE["data"]
    return []

@router.get("/admin/proxy/bank")
async def find_bank(
    search: str = Query(None, description="BIC код или IBAN")
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
    session: AsyncSession = Depends(get_session)
):
    """
    Генерирует описание на основе тегов и возвращает текст.
    Админ может потом его отредактировать и сохранить.
    """
    text = await DescriptionGeneratorService.generate(session, product_id)
    return {"description": text}