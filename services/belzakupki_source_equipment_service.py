"""Read local reviewed request evidence and explicitly append its exact products."""

from hashlib import sha256
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from models import Order, OrderAttachmentLink, OrderProductLink, OrderProposal, ServiceAttachment
from models.tenancy import TenantScope
from schemas_belzakupki_enrichment import (
    ManagerOrderSourceCard, ManagerOrderSourceEquipmentAdd, ManagerOrderSourceEquipmentPreview,
    SourceEquipmentCandidateItem, SourceObjectDraft, SourceOriginalFile, SourceEquipmentPrefillResult,
    SourceSubmissionDraft,
)
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService, _source_identity, _text
from services.belzakupki_equipment_prefill import BelzakupkiEquipmentPrefillService
from services.belzakupki_installation_facts import installation_facts


class SourceEquipmentPreviewChangedError(ValueError):
    pass


class BelzakupkiSourceEquipmentService:
    @staticmethod
    def reviewed_objects(order: Order) -> list[SourceObjectDraft]:
        enrichment = ((order.technical_meta or {}).get("belzakupki") or {}).get("enrichment") or {}
        source, external_id = _source_identity(order)
        if enrichment.get("source") != source or enrichment.get("external_id") != external_id:
            return []
        return [SourceObjectDraft.model_validate(item) for item in enrichment.get("objects") or []]

    @classmethod
    async def card(cls, session: AsyncSession, *, order_id: int, scope: TenantScope) -> ManagerOrderSourceCard:
        order = await BelzakupkiEnrichmentService._order(session, order_id, scope)
        source, external_id = _source_identity(order)
        meta = (order.technical_meta or {}).get("belzakupki") or {}
        tender = meta.get("tender") or {}
        rows = (await session.execute(select(ServiceAttachment).join(
            OrderAttachmentLink, OrderAttachmentLink.attachment_id == ServiceAttachment.id,
        ).where(
            OrderAttachmentLink.order_id == order_id, OrderAttachmentLink.archived_at.is_(None),
            ServiceAttachment.archived_at.is_(None), ServiceAttachment.source == "belzakupki",
        ).order_by(ServiceAttachment.id))).scalars().all()
        originals = [SourceOriginalFile(
            attachment_id=int(row.id), name=row.original_filename,
            document_id=(row.source_meta or {}).get("belzakupki_document_id"), mime_type=row.mime_type,
        ) for row in rows if (row.source_meta or {}).get("external_id") == external_id
                     and (row.source_meta or {}).get("source") == source]
        return ManagerOrderSourceCard(
            order_id=order_id, source=source, external_id=external_id,
            submission=SourceSubmissionDraft.model_validate((meta.get("enrichment") or {}).get("submission") or {}),
            title=_text(tender.get("title"), 1000), source_url=_text(tender.get("source_url"), 2048),
            work_summary=_text((meta.get("enrichment") or {}).get("work_summary"), 10000),
            equipment_details=_text((meta.get("enrichment") or {}).get("equipment_details"), 10000),
            objects=cls.reviewed_objects(order), originals=originals,
            equipment_prefill=(meta.get("enrichment") or {}).get("equipment_prefill"),
            installation_facts=installation_facts(meta.get("enrichment") or {}),
        )

    @classmethod
    async def _preview_for_order(
        cls, session: AsyncSession, *, order: Order, scope: TenantScope, proposal_id: int | None,
    ) -> ManagerOrderSourceEquipmentPreview:
        objects = cls.reviewed_objects(order)
        partial, resolved = await BelzakupkiEquipmentPrefillService.resolve(session, scope=scope, objects=objects)
        proposals = list((await session.execute(select(OrderProposal).where(
            OrderProposal.order_id == order.id, OrderProposal.is_archived.is_(False),
        ).order_by(OrderProposal.sort_order, OrderProposal.id))).scalars().all())
        proposal = next((p for p in proposals if p.id == proposal_id), None) if proposal_id is not None else (
            next((p for p in proposals if p.is_selected), None)
        )
        if proposal_id is not None and proposal is None:
            raise ValueError("Proposal not found")
        lines = list((await session.execute(select(OrderProductLink).where(
            OrderProductLink.order_id == order.id, OrderProductLink.proposal_id == proposal.id,
        ))).scalars().all()) if proposal is not None else []
        history = ((order.technical_meta or {}).get("belzakupki") or {}).get("equipment_prefill_history") or {}
        source, external_id = _source_identity(order)
        items = [SourceEquipmentCandidateItem(**item.model_dump(exclude={"line_id"})) for item in partial.skipped]
        writable = proposal is not None and proposal.status == "draft" and not scope.demo_read_only
        for product_id, (candidate, equipment) in resolved.items():
            quantity = int(equipment.quantity)
            existing = [line for line in lines if line.product_id == product_id]
            existing_qty = sum(int(line.quantity) for line in existing)
            previous = history.get(BelzakupkiEquipmentPrefillService._fingerprint(source, external_id, product_id))
            can_add = False
            can_restore = False
            if order.workflow_type != "sales_installation":
                reason, message = "wrong_scenario", "Добавление товаров из заявки доступно в сценарии «Продажа + монтаж»."
            elif not writable:
                reason, message = "proposal_not_draft", "Выберите доступное для изменений предложение-черновик."
            elif existing:
                reason, message = "existing_line", f"Уже в предложении: {existing_qty}; количество и цена сохранены."
            elif quantity > 2_147_483_647:
                reason, message = "invalid_quantity", "Проверьте слишком большое суммарное количество."
            elif candidate.available_quantity < quantity:
                reason, message = "insufficient_stock", f"Требуется {quantity}, доступно {candidate.available_quantity}; уточните поставку."
            elif candidate.price <= 0:
                reason, message = "missing_price", "Проверьте текущую цену продажи."
            elif previous:
                if previous.get("proposal_id") not in (None, proposal.id):
                    reason, message = "previously_added_elsewhere", "Ранее добавляли в другое предложение. Для выбранного черновика добавьте повторно."
                else:
                    reason, message = "previously_removed", "Ранее переносилось; восстановить можно только явно."
                can_restore = True
            else:
                reason, message = "ready", "Точное совпадение, можно добавить по текущей цене."
                can_add = True
            if candidate.cost is None or candidate.cost <= 0:
                message += " Закупочная стоимость неизвестна."
            items.append(SourceEquipmentCandidateItem(
                **equipment.model_dump(), product_id=product_id, product_title=candidate.product.title,
                price=candidate.price, available_quantity=candidate.available_quantity,
                existing_quantity=existing_qty, reason=reason, message=message,
                can_add=can_add, can_restore=can_restore,
            ))
        warnings = partial.warnings.copy()
        if not objects:
            warnings.append("В заявке нет подтверждённых моделей. Откройте проработку источника и проверьте оборудование.")
        snapshot = {
            "source": source, "external_id": external_id, "objects": [obj.model_dump() for obj in objects],
            "proposal_id": proposal.id if proposal else None, "proposal_status": proposal.status if proposal else None,
            "workflow": order.workflow_type, "items": [item.model_dump() for item in items],
        }
        return ManagerOrderSourceEquipmentPreview(
            order_id=int(order.id), proposal_id=proposal.id if proposal else None,
            proposal_status=proposal.status if proposal else None,
            preview_fingerprint=sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
            items=items, warnings=warnings,
        )

    @classmethod
    async def preview(
        cls, session: AsyncSession, *, order_id: int, scope: TenantScope, proposal_id: int | None = None,
    ) -> ManagerOrderSourceEquipmentPreview:
        order = await BelzakupkiEnrichmentService._order(session, order_id, scope)
        return await cls._preview_for_order(session, order=order, scope=scope, proposal_id=proposal_id)

    @classmethod
    async def add(
        cls, session: AsyncSession, *, order_id: int, scope: TenantScope,
        payload: ManagerOrderSourceEquipmentAdd,
    ) -> SourceEquipmentPrefillResult:
        if scope.demo_read_only:
            raise ValueError("Demo workspace is read-only")
        order = await BelzakupkiEnrichmentService._order(session, order_id, scope, lock=True)
        command_key = sha256(json.dumps({"id": payload.command_id, "proposal_id": payload.proposal_id,
                                       "products": sorted(payload.product_ids), "restore": sorted(payload.restore_removed_product_ids)}, sort_keys=True).encode()).hexdigest()
        commands = dict(((order.technical_meta or {}).get("belzakupki") or {}).get("equipment_prefill_commands") or {})
        if command_key in commands:
            return SourceEquipmentPrefillResult.model_validate(commands[command_key])
        preview = await cls._preview_for_order(session, order=order, scope=scope, proposal_id=payload.proposal_id)
        if preview.preview_fingerprint != payload.preview_fingerprint:
            raise SourceEquipmentPreviewChangedError("Данные заявки, предложения, цена или наличие изменились. Обновите подбор из заявки.")
        ids = set(payload.product_ids)
        restore = set(payload.restore_removed_product_ids)
        if len(ids) != len(payload.product_ids) or not restore.issubset(ids):
            raise ValueError("Invalid product selection")
        allowed = {item.product_id for item in preview.items if item.can_add or (item.can_restore and item.product_id in restore)}
        if not ids.issubset(allowed):
            raise ValueError("Выбранные товары недоступны для добавления; обновите подбор из заявки.")
        source, external_id = _source_identity(order)
        report = await BelzakupkiEquipmentPrefillService.apply(
            session, order=order, scope=scope, source=source, external_id=external_id,
            objects=cls.reviewed_objects(order), proposal_id=payload.proposal_id,
            product_ids=ids, restore_removed_product_ids=restore,
        )
        meta = dict(order.technical_meta or {})
        belzakupki = dict(meta.get("belzakupki") or {})
        enrichment = dict(belzakupki.get("enrichment") or {})
        enrichment["equipment_prefill"] = report.model_dump()
        commands[command_key] = report.model_dump()
        belzakupki["equipment_prefill_commands"] = commands
        belzakupki["enrichment"] = enrichment
        meta["belzakupki"] = belzakupki
        order.technical_meta = meta
        flag_modified(order, "technical_meta")
        await session.commit()
        return report
