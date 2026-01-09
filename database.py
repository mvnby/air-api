from sqlmodel import SQLModel, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Product

DB_NAME = "air_conditioners.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DB_NAME}"

# Async Engine
engine = create_async_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

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