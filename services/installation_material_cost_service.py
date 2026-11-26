from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from crud import installation_materials as prices
from models.installation_material import InstallationMaterialPrice
from models.tenancy import TenantScope
from schemas_installation_materials import (
    InstallationMaterialCostInput,
    InstallationMaterialCostLine,
    InstallationMaterialCostResult,
    InstallationMaterialPriceInput,
    InstallationMaterialPriceItem,
    InstallationMaterialPriceList,
    InstallationMaterialPriceUpdate,
)


async def list_material_prices(
    session: AsyncSession, scope: TenantScope, *, query: str, offset: int, limit: int,
) -> InstallationMaterialPriceList:
    rows = await prices.list_prices(session, scope.tenant_id, query=query.strip(), offset=offset, limit=limit + 1)
    return InstallationMaterialPriceList(
        items=[InstallationMaterialPriceItem.model_validate(row) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )


async def save_material_price(
    session: AsyncSession, scope: TenantScope, payload: InstallationMaterialPriceInput,
    *, price_id: int | None = None,
) -> InstallationMaterialPriceItem:
    if scope.demo_read_only:
        raise HTTPException(403, "В демо-компании доступны только расчёты")
    values = payload.model_dump(exclude={"expected_version"})
    values["source_url"] = str(payload.source_url) if payload.source_url else None
    if price_id is None:
        price = InstallationMaterialPrice(tenant_id=scope.tenant_id, **values)
        session.add(price)
    else:
        price = await prices.lock_price(session, scope.tenant_id, price_id)
        if price is None:
            raise HTTPException(404, "Закупочная цена не найдена")
        if not isinstance(payload, InstallationMaterialPriceUpdate) or price.version != payload.expected_version:
            raise HTTPException(409, "Цена уже обновлена. Загрузите актуальную версию.")
        price.sqlmodel_update(values)
        price.version += 1
    try:
        await session.flush()
        result = InstallationMaterialPriceItem.model_validate(price)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(409, "Такой материал уже есть у этого поставщика") from exc
    return result


async def calculate_material_cost(
    session: AsyncSession, scope: TenantScope, payload: InstallationMaterialCostInput,
) -> InstallationMaterialCostResult:
    rows = await prices.prices_by_id(session, scope.tenant_id, [item.price_id for item in payload.items])
    if len(rows) != len(payload.items):
        raise HTTPException(404, "Одна или несколько закупочных цен недоступны")
    lines = []
    for item in payload.items:
        price = rows[item.price_id]
        if price.version != item.expected_version:
            raise HTTPException(409, "Закупочная цена изменилась. Добавьте актуальную позицию в расчёт.")
        total = (price.pack_price_byn * item.quantity / price.pack_quantity).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        lines.append(InstallationMaterialCostLine(
            price_id=item.price_id, quantity=item.quantity,
            price=InstallationMaterialPriceItem.model_validate(price), total_byn=total,
        ))
    return InstallationMaterialCostResult(
        items=lines, total_byn=sum((line.total_byn for line in lines), start=Decimal("0.00")),
    )
