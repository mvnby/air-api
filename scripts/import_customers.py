import csv
import asyncio
import os
from sqlalchemy import select
from core.database import async_session_maker
from models import Customer, CustomerType
from services.tenant_scope_service import (
    SystemTenantScopeResolver,
    tenant_or_legacy_owner_scope_clause,
)

CSV_FILE = "контрагенты - main.csv"

async def import_customers():
    if not os.path.exists(CSV_FILE):
        print(f"Error: File {CSV_FILE} not found!")
        return

    async with async_session_maker() as session:
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        print(f"Starting import from {CSV_FILE}...")
        
        count_new = 0
        count_skipped = 0
        count_errors = 0

        with open(CSV_FILE, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    name = row.get("Контрагент (плательщик)", "").strip()
                    inn = row.get("УНН", "").strip()
                    
                    if not name:
                        print(f"Skipping row {row.get('ID')}: name is missing")
                        count_errors += 1
                        continue

                    # Deduplication by INN (if present)
                    if inn:
                        stmt = select(Customer).where(
                            Customer.inn == inn,
                            tenant_or_legacy_owner_scope_clause(
                                Customer,
                                tenant_scope,
                            ),
                        )
                        result = await session.execute(stmt)
                        existing = result.scalar_one_or_none()
                        
                        if existing:
                            # Update empty fields if necessary
                            needs_update = False
                            if not existing.iban and row.get("Расчетный счет"):
                                existing.iban = row.get("Расчетный счет").strip()
                                needs_update = True
                            if not existing.bank_name and row.get("Наименование и адрес банка"):
                                existing.bank_name = row.get("Наименование и адрес банка").strip()
                                needs_update = True
                            
                            if needs_update:
                                session.add(existing)
                                
                            # print(f"Customer with INN {inn} already exists ({name}). Skipping.")
                            count_skipped += 1
                            continue
                    
                    # Create new customer
                    customer = Customer(
                        tenant_id=tenant_scope.tenant_id,
                        name=name,
                        full_legal_name=name,
                        inn=inn,
                        phone="",  # Not in CSV, but required by model
                        email=row.get("Email", "").strip(),
                        type=CustomerType.company,
                        legal_address=row.get("Адрес", "").strip(),
                        actual_address=row.get("Адрес", "").strip(),
                        iban=row.get("Расчетный счет", "").strip(),
                        bank_name=row.get("Наименование и адрес банка", "").strip(),
                        bic=row.get("Код банка", "").strip(),
                        signer_position="Директора",
                        acting_basis="Устава"
                    )
                    
                    session.add(customer)
                    count_new += 1
                    
                    if count_new % 20 == 0:
                        print(f"Imported {count_new} customers...")
                        await session.commit()

                except Exception as e:
                    print(f"Error processing row {row.get('ID')}: {e}")
                    count_errors += 1

        await session.commit()
        print("=" * 50)
        print(f"Import finished!")
        print(f"New:     {count_new}")
        print(f"Skipped: {count_skipped} (already exist)")
        print(f"Errors:  {count_errors}")
        print("=" * 50)

if __name__ == "__main__":
    asyncio.run(import_customers())
