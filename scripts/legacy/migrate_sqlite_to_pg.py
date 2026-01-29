import os
import shutil
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlmodel import SQLModel, create_engine, Session, select, text

# Import all models to ensure metadata is registered
from models import (
    TagGroup, Tag, Product, Article, Customer, Installer, Service,
    GlobalConfig, Cart, Order, ProductTagLink, OrderProductLink,
    OrderServiceLink, OrderInstaller, CartItem, Favorite
)
from core.config import settings

def main():
    load_dotenv()
    
    # 1. Backup SQLite DB
    sqlite_db_path = Path("air_conditioners.db")
    backup_path = Path("air_conditioners.db.bak")
    
    if sqlite_db_path.exists():
        print(f"Backing up database to {backup_path}...")
        shutil.copy(sqlite_db_path, backup_path)
    else:
        print(f"Warning: {sqlite_db_path} not found. Assuming fresh start or partial migration.")
        # We might still want to proceed if we just want to init Postgres, 
        # but the task is "migrate", so let's warn.
    
    # 2. Setup Engines
    # SQLite (Source)
    sqlite_url = "sqlite:///./air_conditioners.db"
    sqlite_engine = create_engine(sqlite_url)
    
    # Postgres (Target) - Construct synchronous URL from env vars
    # We need a synchronous driver (psycopg2) for the migration
    # Use environment variables or defaults
    pg_user = os.getenv("POSTGRES_USER", "mvnadmin")
    pg_password = os.getenv("POSTGRES_PASSWORD", "securepass")
    pg_server = os.getenv("POSTGRES_SERVER", "db")  # 'db' is the docker service name
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "air_conditioners")
    
    pg_url = f"postgresql://{pg_user}:{pg_password}@{pg_server}:{pg_port}/{pg_db}"
    pg_engine = create_engine(pg_url)
    
    print(f"Source: {sqlite_url}")
    print(f"Target: {pg_url}")
    
    # 3. Create Tables in Postgres
    print("Creating tables in Postgres...")
    SQLModel.metadata.create_all(pg_engine)
    
    # 4. Define Migration Order
    # Order matters due to Foreign Keys
    models_ordered = [
        TagGroup,
        Tag,
        Product,
        Article,
        Customer,
        Installer,
        Service,
        GlobalConfig,
        Cart,
        Order,
        ProductTagLink,
        OrderProductLink,
        OrderServiceLink,
        OrderInstaller,
        CartItem,
        Favorite
    ]
    
    # 5. Migrate Data
    with Session(sqlite_engine) as src_session, Session(pg_engine) as tgt_session:
        for model in models_ordered:
            table_name = model.__tablename__
            print(f"Migrating {table_name}...")
            
            # Read from SQLite
            stm = select(model)
            results = src_session.exec(stm).all()
            
            count = 0
            for row in results:
                # Merge ensures valid handling but for bulk migration of clean data, add is faster.
                # However, re-attaching objects from one session to another is tricky.
                # We interpret the row as a dict and create a new instance to detach entirely from source session
                data = row.model_dump()
                new_obj = model(**data)
                tgt_session.add(new_obj)
                count += 1
            
            tgt_session.commit()
            print(f"  -> Migrated {count} rows.")
            
            # 6. Reset Sequences (for ID auto-increment)
            # This is specific to Postgres
            if hasattr(model, "id"):
                print(f"  -> Resetting sequence for {table_name}...")
                try:
                    # Get the max id
                    max_id = tgt_session.exec(text(f"SELECT MAX(id) FROM {table_name}")).first()
                    max_id = max_id[0] if max_id and max_id[0] is not None else 0
                    next_id = max_id + 1
                    
                    # Reset sequence
                    # Assumption: sequence name is table_name_id_seq by default in Postgres/SQLAlchemy
                    # But better usage is pg_get_serial_sequence
                    seq_reset_query = text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), {next_id}, false);")
                    tgt_session.exec(seq_reset_query)
                    tgt_session.commit()
                except Exception as e:
                    print(f"  -> Warning: Could not reset sequence for {table_name}: {e}")
                    tgt_session.rollback()

    print("Migration completed successfully!")

if __name__ == "__main__":
    main()
