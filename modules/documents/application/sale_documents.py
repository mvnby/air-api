"""Customer-facing sale receipt and equipment warranty facts frozen at draft creation."""

from datetime import datetime, time

from sqlalchemy import and_, exists, or_
from sqlmodel import select

from services.warranty_coverage_service import WarrantyCoverageService
from models import CustomerBranch, CustomerEquipment, EquipmentComponent, EquipmentOrderLink, EquipmentWarrantyCoverage

def _text(value):
    return str(value or "").strip()


def _equipment_name(item):
    model = _text(item.model)
    brand = _text(item.brand)
    if model and brand and brand.casefold() not in model.casefold():
        model = f"{brand} {model}".strip()
    return model or _text(getattr(item, "display_name", None) or getattr(item, "title", None))


async def _warranty_facts(session, *, order, equipment_id, product_links, issue_date):
    order_links = exists().where(
        EquipmentOrderLink.order_id == order.id,
        EquipmentOrderLink.equipment_id == CustomerEquipment.id,
    )
    item = await session.scalar(select(CustomerEquipment).where(
        CustomerEquipment.id == equipment_id, CustomerEquipment.customer_id == order.customer_id,
        CustomerEquipment.is_archived.is_(False),
        CustomerEquipment.equipment_source.not_in(("installed_by_us", "customer_owned")),
        or_(order_links.where(EquipmentOrderLink.role == "sale"),
            and_(CustomerEquipment.source_order_id == order.id, ~order_links)),
    ))
    if item is None or item.warranty_mode == "none":
        raise ValueError("Выберите оборудование с гарантией из этой продажи")
    active_proposals = [p for p in order.proposals if not p.is_archived]
    if active_proposals:
        if item.catalog_product_id is None and len(active_proposals) > 1:
            raise ValueError("Без связи с товаром нельзя определить предложение оборудования")
        if item.catalog_product_id is not None and item.catalog_product_id not in {line.product_id for line in product_links}:
            raise ValueError("Оборудование не относится к выбранному предложению")
    if order.customer_branch_id and item.customer_branch_id and order.customer_branch_id != item.customer_branch_id:
        raise ValueError("Оборудование относится к другому объекту клиента")
    covers = list(await session.scalars(select(EquipmentWarrantyCoverage).where(
        EquipmentWarrantyCoverage.equipment_id == item.id,
        or_(EquipmentWarrantyCoverage.component_id.is_(None), EquipmentWarrantyCoverage.component_id.in_(
            select(EquipmentComponent.id).where(EquipmentComponent.equipment_id == item.id, EquipmentComponent.is_archived.is_(False))
        )),
    )))
    start, end, terms = item.warranty_started_at, item.warranty_expires_at, item.warranty_terms
    goods_covers = [c for c in covers if c.coverage_type in {"supplier", "legacy"}]
    if covers and not goods_covers:
        raise ValueError("В карточке нет отдельного гарантийного покрытия оборудования")
    if any(c.component_id is not None for c in goods_covers):
        raise ValueError("У блоков отдельные гарантийные покрытия. Для общего талона требуется единый срок для всей системы")
    if goods_covers:
        valid = [c for c in goods_covers if c.decision_status != "voided"]
        if len(valid) != 1:
            raise ValueError("Проверьте действующее гарантийное покрытие оборудования в карточке")
        coverage = valid[0]
        status = WarrantyCoverageService.coverage_status(coverage, now=datetime.combine(issue_date, time.min))
        if status["requires_manager_decision"]:
            raise ValueError("По гарантии требуется решение менеджера о техническом обслуживании")
        start, end, terms = coverage.starts_at, coverage.expires_at, coverage.terms_snapshot
        if coverage.maintenance_required:
            maintenance = "Требуется техническое обслуживание"
            if coverage.maintenance_interval_months:
                maintenance += f" каждые {coverage.maintenance_interval_months} мес."
            provider = {"mvn": "у продавца", "authorized": "у авторизованного исполнителя"}.get(coverage.allowed_maintenance_provider)
            if provider:
                maintenance += " " + provider
            if coverage.grace_period_days:
                maintenance += f". Допустимая отсрочка — {coverage.grace_period_days} дн."
            terms = "\n".join(filter(None, (_text(terms), maintenance)))
    if start is None or end is None or start.date() > end.date():
        raise ValueError("Заполните даты начала и окончания гарантии в карточке оборудования")
    name = _equipment_name(item)
    if not name:
        raise ValueError("Укажите модель или название в карточке оборудования")
    components = await session.scalars(select(EquipmentComponent).where(
        EquipmentComponent.equipment_id == item.id, EquipmentComponent.is_archived.is_(False),
    ).order_by(EquipmentComponent.id))
    component_lines = []
    for comp in components:
        parts = list(dict.fromkeys(filter(None, (_text(comp.title), _equipment_name(comp)))))
        if comp.serial:
            parts.append("сер. № " + _text(comp.serial))
        if parts:
            component_lines.append(" · ".join(parts))
    site = ""
    if item.customer_branch_id:
        site = _text(await session.scalar(select(CustomerBranch.delivery_address).where(
            CustomerBranch.id == item.customer_branch_id, CustomerBranch.customer_id == order.customer_id,
        )))
    address = site or _text(order.delivery_address) or _text(getattr(order.customer_branch, "delivery_address", None))
    location = _text(item.location_hint)
    if location and location != address:
        address = ", ".join(filter(None, (address, location)))
    return {
        "equipment.display_name": name, "equipment.brand": _text(item.brand),
        "equipment.model": _text(item.model), "equipment.serial": _text(item.serial),
        "certificate.components": "\n".join(component_lines),
        "certificate.started_on": start.strftime("%d.%m.%Y"), "certificate.expires_on": end.strftime("%d.%m.%Y"),
        "warranty.goods.terms": _text(terms),
        "order.object_address": address,
    }


async def fill_sale_snapshot(session, *, selection, order, product_links, snapshot):
    values, conditions = snapshot["values"], snapshot["conditions"]
    if order.customer is None or order.customer.tenant_id != order.tenant_id or not _text(values.get("customer.full_name")):
        raise ValueError("Для документа укажите покупателя в заказе")
    for key in ("warranty.goods.months", "warranty.goods.terms", "warranty.work.months", "warranty.work.terms"):
        values[key] = ""
    for key in ("warranty.goods.present", "warranty.work.present", "warranty.any_present"):
        conditions[key] = False
    public_offer = values["customer.entity_type"] == "individual"
    if selection.document_type == "retail_receipt":
        if not public_offer:
            raise ValueError("Товарный чек оформляется для физического лица")
        if not product_links:
            raise ValueError("В выбранном предложении нет товаров для товарного чека")
        values["receipt.note"] = _text(selection.receipt_note)
        conditions["receipt.has_note"] = bool(values["receipt.note"])
    else:
        facts = await _warranty_facts(session, order=order, equipment_id=selection.warranty_equipment_id,
                                     product_links=product_links, issue_date=selection.issue_date)
        facts["order.object_address"] = facts["order.object_address"] or values.get("order.object_address", "")
        values.update(facts)
        snapshot["meta"]["warranty_equipment_id"] = selection.warranty_equipment_id
        snapshot["table_rows"] = {}
        conditions.update({
            "certificate.has_components": bool(facts["certificate.components"]),
            "equipment.has_serial": bool(facts["equipment.serial"]),
            "warranty.goods.present": True, "warranty.any_present": True,
            "certificate.has_terms": bool(facts["warranty.goods.terms"]),
            "order.has_object_address": bool(facts["order.object_address"]),
        })
    if public_offer and not all(values.get(k) for k in ("offer.url", "offer.version", "offer.published_on")):
        raise ValueError("Заполните ссылку, версию и дату публичной оферты в реквизитах продавца")
    conditions["sale.has_offer"] = public_offer
