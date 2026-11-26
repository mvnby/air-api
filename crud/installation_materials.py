from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.installation_material import InstallationMaterialPrice


async def list_prices(
    session: AsyncSession, tenant_id: int, *, query: str, offset: int, limit: int,
) -> list[InstallationMaterialPrice]:
    statement = select(InstallationMaterialPrice).where(InstallationMaterialPrice.tenant_id == tenant_id)
    if query:
        value = query.lower()
        statement = statement.where(or_(
            func.lower(InstallationMaterialPrice.title).contains(value, autoescape=True),
            func.lower(InstallationMaterialPrice.supplier).contains(value, autoescape=True),
        ))
    return list((await session.scalars(statement.order_by(
        InstallationMaterialPrice.title, InstallationMaterialPrice.supplier, InstallationMaterialPrice.id,
    ).offset(offset).limit(limit))).all())


async def prices_by_id(
    session: AsyncSession, tenant_id: int, ids: list[int],
) -> dict[int, InstallationMaterialPrice]:
    rows = await session.scalars(select(InstallationMaterialPrice).where(
        InstallationMaterialPrice.tenant_id == tenant_id, InstallationMaterialPrice.id.in_(ids),
    ))
    return {row.id: row for row in rows}


async def lock_price(session: AsyncSession, tenant_id: int, price_id: int) -> InstallationMaterialPrice | None:
    return await session.scalar(select(InstallationMaterialPrice).where(
        InstallationMaterialPrice.tenant_id == tenant_id, InstallationMaterialPrice.id == price_id,
    ).with_for_update().execution_options(populate_existing=True))
