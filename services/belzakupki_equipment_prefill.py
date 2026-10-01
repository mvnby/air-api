"""Append reviewed tender equipment through the scoped catalog decision boundary."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from models import Brand, Order, OrderProductLink, Product, TenantOffer
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import (
    SourceEquipmentDraft, SourceEquipmentPrefillItem, SourceEquipmentPrefillResult,
    SourceObjectDraft,
)
from services.catalog_decision_projection import CatalogDecisionQueryService
from services.fx_rate_service import FxRateService
from services.order_service import OrderService


_DASHES = "‐‑‒–—−"
_WHITESPACE = " \t\n\r\v\f\u00a0\u202f"


def normalize_model(value: object) -> str:
    """Only casing, whitespace and equivalent dash glyphs are interchangeable."""
    return re.sub(r"\s+", "", str(value or "").translate(str.maketrans(_DASHES, "-" * len(_DASHES)))).casefold()


def _normalized_sql(expression):
    for character in _DASHES:
        expression = func.replace(expression, character, "-")
    for character in _WHITESPACE:
        expression = func.replace(expression, character, "")
    return func.lower(expression)


def full_model_matches(product: Product, model: str) -> bool:
    """A canonical full model wins; indoor/outdoor component names never qualify."""
    specs = product.specs or {}
    canonical = str(specs.get("model") or "").strip()
    if canonical:
        return normalize_model(canonical) == model
    indoor = normalize_model(specs.get("model_indoor"))
    outdoor = normalize_model(specs.get("model_outdoor"))
    if indoor and outdoor:
        pair = f"{indoor}/{outdoor}"
        if pair == model:
            return True
        # The explicit (WF) suffix describes built-in Wi-Fi in reviewed tender
        # pairs. Accept this one alias only with both canonical component models
        # and affirmative normalized Wi-Fi data; other qualifiers stay literal.
        builtin = specs.get("wifi_state") == "builtin" and specs.get("wifi_builtin") is True
        return builtin and re.sub(r"\(wf\)(?=/)", "", model, count=1) == pair
    # Legacy products sometimes have only a model token in their title. Keep
    # token boundaries, slash pairs and suffixes: A12 cannot match A12-X or A12/B12.
    title = product.title.translate(str.maketrans(_DASHES, "-" * len(_DASHES))).casefold()
    if not re.search(r"\d", model):
        return False
    literal = r"\s*".join(re.escape(character) for character in model)
    # A following slash/dash or optional feature suffix means the requested
    # identifier is only a component/prefix, not the full product model.
    pattern = rf"(?<![\w./_-]){literal}(?![\w./_-])(?!\s*(?:[/._-]|\())"
    return re.search(pattern, title) is not None


@dataclass(frozen=True)
class ExactCatalogCandidate:
    product: Product
    brand: str | None
    available_quantity: int
    price: int
    cost: int | None


class BelzakupkiEquipmentPrefillService:
    """Stage lines, report and provenance in the caller's locked order transaction."""

    @staticmethod
    async def candidates(
        session: AsyncSession, *, scope: TenantScope, models: set[str],
    ) -> list[ExactCatalogCandidate]:
        if not models:
            return []
        catalog = CatalogDecisionQueryService
        metrics = catalog._metrics_cte(usd_byn_rate=await FxRateService.get_supplier_usd_byn_rate(session))
        stock = catalog._local_stock_cte()
        retail = catalog._retail_price(scope)
        cost = catalog._purchase_cost(await catalog._uses_demo_cost(session, scope), metrics, retail)
        canonical_model = _normalized_sql(catalog._json_text(session, "model"))
        pair = _normalized_sql(catalog._json_text(session, "model_indoor")).concat("/").concat(
            _normalized_sql(catalog._json_text(session, "model_outdoor")),
        )
        search_models = models | {re.sub(r"\(wf\)(?=/)", "", model, count=1) for model in models}
        title = _normalized_sql(Product.title)
        statement = (
            select(
                Product, Brand.title.label("brand_title"),
                retail.label("retail_price"), cost.label("purchase_cost"),
                (func.coalesce(metrics.c.supplier_qty, 0) + func.coalesce(stock.c.local_qty, 0)).label("available_quantity"),
            )
            .outerjoin(Brand, Brand.id == Product.brand_id)
            .outerjoin(metrics, metrics.c.product_id == Product.id)
            .outerjoin(stock, stock.c.product_id == Product.id)
            .where(catalog._complete_split_condition(session), or_(
                canonical_model.in_(models), pair.in_(search_models),
                *(title.contains(model, autoescape=True) for model in sorted(search_models)),
            ))
        )
        if not scope.is_system:
            statement = statement.join(TenantOffer, TenantOffer.product_id == Product.id).where(
                *catalog._visible_offer_conditions(scope),
            )
        return [ExactCatalogCandidate(
            product=row[0], brand=row.brand_title or (row[0].specs or {}).get("brand"),
            available_quantity=int(row.available_quantity or 0),
            price=int(round(float(row.retail_price or 0))),
            cost=int(round(float(row.purchase_cost))) if row.purchase_cost is not None else None,
        ) for row in (await session.execute(statement)).all()]

    @staticmethod
    def _fingerprint(source: str, external_id: str, product_id: int) -> str:
        # Quantity/address are deliberately excluded: reapplying a corrected
        # tender never overwrites manager edits or recreates a removed line.
        return sha256(f"{source}:{external_id}:{product_id}".encode()).hexdigest()

    @classmethod
    async def apply(
        cls, session: AsyncSession, *, order: Order, scope: TenantScope,
        source: str, external_id: str, objects: list[SourceObjectDraft],
    ) -> SourceEquipmentPrefillResult:
        if scope.demo_read_only:
            raise ValueError("Demo workspace is read-only")
        result = SourceEquipmentPrefillResult()
        grouped: dict[tuple[str, str], SourceEquipmentDraft] = {}

        def skip(equipment: SourceEquipmentDraft, reason: str, message: str, product_id: int | None = None):
            result.skipped.append(SourceEquipmentPrefillItem(
                **equipment.model_dump(), product_id=product_id, reason=reason, message=message,
            ))
            if message not in result.warnings:
                result.warnings.append(message)

        for obj in objects:
            for equipment in obj.equipment:
                if not normalize_model(equipment.model) or equipment.quantity is None:
                    skip(equipment, "incomplete", f"{equipment.brand or ''} {equipment.model or 'Модель не указана'}: укажите полную модель и количество.".strip())
                    continue
                key = (normalize_model(equipment.brand), normalize_model(equipment.model))
                if key in grouped:
                    grouped[key].quantity = int(grouped[key].quantity or 0) + equipment.quantity
                else:
                    grouped[key] = equipment.model_copy(deep=True)
        if not grouped:
            return result

        candidates = await cls.candidates(session, scope=scope, models={key[1] for key in grouped})
        resolved: dict[int, tuple[ExactCatalogCandidate, SourceEquipmentDraft]] = {}
        for (brand, model), equipment in grouped.items():
            matches = [candidate for candidate in candidates if
                       full_model_matches(candidate.product, model)
                       and (not brand or normalize_model(candidate.brand) == brand)]
            label = " ".join(filter(None, [equipment.brand, equipment.model]))
            if len(matches) != 1:
                reason = "ambiguous" if matches else "not_found"
                message = (f"{label}: найдено несколько точных совпадений, выберите товар вручную."
                           if matches else f"{label}: точного совпадения в доступном каталоге нет, подберите товар вручную.")
                skip(equipment, reason, message)
                continue
            candidate = matches[0]
            product_id = int(candidate.product.id)
            if product_id in resolved:
                resolved[product_id][1].quantity += int(equipment.quantity)
            else:
                resolved[product_id] = (candidate, equipment.model_copy(deep=True))
        if not resolved:
            return result

        await session.refresh(order, attribute_names=["proposals", "product_links", "service_links"])
        proposal = await OrderService.ensure_default_proposal(session, order)
        result.proposal_id = int(proposal.id)
        if proposal.status != "draft" or proposal.is_archived:
            for product_id, (_, equipment) in resolved.items():
                skip(equipment, "proposal_not_draft", "Выбранное предложение уже отправлено или подтверждено; добавьте оборудование вручную в черновик.", product_id)
            return result
        lines = list((await session.execute(select(OrderProductLink).where(
            OrderProductLink.order_id == order.id, OrderProductLink.proposal_id == proposal.id,
        ))).scalars().all())
        source_meta = dict(order.technical_meta or {})
        belzakupki = dict(source_meta.get("belzakupki") or {})
        history = dict(belzakupki.get("equipment_prefill_history") or {})
        for product_id, (candidate, equipment) in resolved.items():
            fingerprint = cls._fingerprint(source, external_id, product_id)
            label = " ".join(filter(None, [equipment.brand, equipment.model]))
            if fingerprint in history:
                skip(equipment, "already_processed", f"{label}: уже переносилось в предложение; изменения менеджера сохранены. Проверьте текущие строки вручную.", product_id)
                continue
            existing = next((line for line in lines if line.product_id == product_id), None)
            if existing:
                history[fingerprint] = {"product_id": product_id, "proposal_id": int(proposal.id), "line_id": existing.id, "quantity": equipment.quantity, "source": source, "external_id": external_id, "action": "existing_line"}
                skip(equipment, "existing_line", f"{label}: товар уже есть в выбранном предложении; количество и цена сохранены. Проверьте количество вручную.", product_id)
                continue
            quantity = int(equipment.quantity)
            if quantity > 2_147_483_647:
                skip(equipment, "invalid_quantity", f"{label}: суммарное количество слишком большое; проверьте количество вручную.", product_id)
                continue
            if candidate.available_quantity < quantity:
                skip(equipment, "insufficient_stock", f"{label}: требуется {quantity}, доступно {candidate.available_quantity}; уточните поставку или подберите замену.", product_id)
                continue
            if candidate.price <= 0:
                skip(equipment, "missing_price", f"{label}: актуальная цена продажи неизвестна; проверьте цену вручную.", product_id)
                continue
            if candidate.cost is None or candidate.cost <= 0:
                result.warnings.append(f"{label}: закупочная стоимость неизвестна; проверьте себестоимость в предложении.")
            line = OrderProductLink(
                order_id=int(order.id), proposal_id=int(proposal.id), product_id=product_id,
                quantity=quantity, price=candidate.price, cost=candidate.cost or 0,
                title_snapshot=candidate.product.title, currency_snapshot="BYN",
            )
            session.add(line)
            await session.flush()
            history[fingerprint] = {"product_id": product_id, "proposal_id": int(proposal.id), "line_id": int(line.id), "quantity": quantity, "source": source, "external_id": external_id, "model": equipment.model, "brand": equipment.brand, "action": "added"}
            result.added.append(SourceEquipmentPrefillItem(
                **equipment.model_dump(), product_id=product_id, line_id=int(line.id), reason="added",
                message=f"{label} × {quantity}: добавлено в черновик по текущей цене каталога.",
            ))
        belzakupki["equipment_prefill_history"] = history
        source_meta["belzakupki"] = belzakupki
        order.technical_meta = source_meta
        flag_modified(order, "technical_meta")
        if result.added:
            await OrderService._refresh_order_financials(session, order)
        return result
