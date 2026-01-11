from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Product, Order, Favorite
from core.config import settings
from core.logger import logger

# Async Engine
engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

# Async Session Factory
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # Uncomment to reset
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession: # type: ignore
    async with async_session_maker() as session:
        yield session

from sqlalchemy.orm import selectinload

# --- ASYNC HELPERS (FOR BOT) ---

async def get_all_products():
    async with async_session_maker() as session:
        # Load tags eagerly
        statement = select(Product).where(Product.is_published == True).options(selectinload(Product.tags))
        results = await session.execute(statement)
        products = results.scalars().all()
        
        # Manually flattening tags to strings for bot backward compatibility
        items = []
        for p in products:
            data = p.model_dump()
            data['categories'] = [t.title for t in p.tags] # Compatibility with bot
            items.append(data)
        return items

async def get_products_by_area(area: int):
    async with async_session_maker() as session:
        statement = select(Product).where(
            Product.is_published == True,
            Product.area >= area,
            Product.area <= area + 10
        ).options(selectinload(Product.tags))
        results = await session.execute(statement)
        products = results.scalars().all()
        
        items = []
        for p in products:
            data = p.model_dump()
            data['categories'] = [t.title for t in p.tags]
            items.append(data)
        return items

async def search_products(query: str = None, is_inverter: bool = None):
    async with async_session_maker() as session:
        # Start with base query
        statement = select(Product).where(Product.is_published == True).options(selectinload(Product.tags))
        
        # 1. Inverter Filter (if specified, do it early)
        if is_inverter:
            from models import Tag
            statement = statement.join(Product.tags).where(Tag.slug == "inverter")
            
        results = await session.execute(statement)
        products = results.scalars().all()
        
        # 2. Text Search with Fuzzy matching
        if query:
            from thefuzz import process
            # Extract titles to match against
            choices = {p.id: p.title for p in products}
            # Get top matches
            matches = process.extract(query, choices, limit=10)
            
            # Filter and sort products based on fuzzy matches (Lowered threshold for brand/short searches)
            matched_ids = [m[2] for m in matches if m[1] >= 50]
            # Maintain fuzzy order
            id_map = {p.id: p for p in products}
            products = [id_map[pid] for pid in matched_ids if pid in id_map]

        # Format for bot
        items = []
        for p in products:
            data = p.model_dump()
            data['categories'] = [t.title for t in p.tags]
            items.append(data)
        return items

async def get_product_by_id(product_id: int):
    async with async_session_maker() as session:
        statement = select(Product).where(Product.id == product_id).options(selectinload(Product.tags))
        results = await session.execute(statement)
        product = results.scalar_one_or_none()
        
        if product:
            data = product.model_dump()
            data['categories'] = [t.title for t in product.tags]
            return data
        return None

async def update_product_price(product_id: int, new_price: int):
    async with async_session_maker() as session:
        product = await session.get(Product, product_id)
        if product:
            product.price = new_price
            session.add(product)
            await session.commit()
            return True
        return False

async def delete_product(product_id: int):
    async with async_session_maker() as session:
        product = await session.get(Product, product_id)
        if product:
            await session.delete(product)
            await session.commit()
            return True
        return False

# --- ORDER OPERATIONS ---

async def create_order(user_id: int, product_id: int, username: str = None, full_name: str = None, phone: str = None):
    async with async_session_maker() as session:
        order = Order(
            user_id=user_id,
            product_id=product_id,
            username=username,
            full_name=full_name,
            phone=phone
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order

async def get_all_orders():
    async with async_session_maker() as session:
        statement = select(Order).options(selectinload(Order.product)).order_by(Order.created_at.desc())
        results = await session.execute(statement)
        return results.scalars().all()

async def update_order_status(order_id: int, new_status: str):
    async with async_session_maker() as session:
        order = await session.get(Order, order_id)
        if order:
            order.status = new_status
            session.add(order)
            await session.commit()
            return True
        return False
# --- FAVORITES ---

async def toggle_favorite(user_id: int, product_id: int) -> bool:
    """Returns True if added, False if removed"""
    async with async_session_maker() as session:
        stmt = select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()
        
        if item:
            await session.delete(item)
            await session.commit()
            return False
        else:
            fav = Favorite(user_id=user_id, product_id=product_id)
            session.add(fav)
            await session.commit()
            return True

async def is_favorite(user_id: int, product_id: int) -> bool:
    async with async_session_maker() as session:
        stmt = select(Favorite).where(Favorite.user_id == user_id, Favorite.product_id == product_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none() is not None

async def get_favorites(user_id: int):
    async with async_session_maker() as session:
        stmt = select(Favorite).where(Favorite.user_id == user_id).options(selectinload(Favorite.product).selectinload(Product.tags))
        res = await session.execute(stmt)
        favs = res.scalars().all()
        
        items = []
        for f in favs:
            if f.product:
                data = f.product.model_dump()
                data['categories'] = [t.title for t in f.product.tags]
                items.append(data)
        return items
