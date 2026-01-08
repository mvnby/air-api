from sqlmodel import SQLModel, create_engine, Session, select
from models import Product

DB_NAME = "air_conditioners.db"
DATABASE_URL = f"sqlite:///{DB_NAME}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

# --- ФУНКЦИИ ДЛЯ БОТА ---

def get_all_products():
    with Session(engine) as session:
        statement = select(Product).where(Product.is_published == True)
        results = session.exec(statement).all()
        return [p.model_dump() for p in results]

def get_products_by_area(area: int):
    with Session(engine) as session:
        # Диапазон поиска: ищем точное совпадение или чуть больше (+10 м2)
        statement = select(Product).where(
            Product.is_published == True,
            Product.area >= area,
            Product.area <= area + 10
        )
        results = session.exec(statement).all()
        return [p.model_dump() for p in results]

def get_product_by_id(product_id: int):
    with Session(engine) as session:
        product = session.get(Product, product_id)
        return product.model_dump() if product else None

def update_product_price(product_id: int, new_price: int):
    with Session(engine) as session:
        product = session.get(Product, product_id)
        if product:
            product.price = new_price
            session.add(product)
            session.commit()
            return True
        return False

def delete_product(product_id: int):
    with Session(engine) as session:
        product = session.get(Product, product_id)
        if product:
            session.delete(product)
            session.commit()
            return True
        return False