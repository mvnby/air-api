import json
from typing import Any, Iterable, Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    Customer,
    DocumentTemplate,
    DocumentTemplateActLink,
    DocumentTemplateCustomerLink,
    GlobalConfig,
    Order,
    OrderDocument,
)
from services.document_role_service import DocumentRoleService
from services.documents.base import DOC_NAMES, TEMPLATES


class DocumentTemplateService:
    MANAGED_TYPES = {"contract", "act", "invoice", "defect_act", "retail_receipt", "service_act", "maintenance_service_act", "warranty_certificate"}

    @staticmethod
    def _normalize_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _normalize_doc_type(raw: object) -> str:
        doc_type = str(raw or "").strip()
        if doc_type not in DocumentTemplateService.MANAGED_TYPES:
            raise ValueError(f"Unsupported document template type: {doc_type}")
        return doc_type

    @staticmethod
    def _serialize_template(template: DocumentTemplate) -> dict[str, Any]:
        return {
            "id": template.google_template_id,
            "document_template_id": template.id,
            "name": template.name,
            "doc_type": template.doc_type,
            "document_role_type": DocumentRoleService.normalize_role_type(template.document_role_type),
            "description": template.description,
            "base_document_type_label": template.base_document_type_label,
            "is_default": bool(template.is_default),
            "is_active": bool(template.is_active),
            "is_open_contract": bool(template.is_open_contract),
            "client_restricted": bool(template.client_restricted),
            "sort_order": int(template.sort_order or 0),
            "customer_ids": [int(customer.id) for customer in template.customers if customer.id is not None],
            "linked_contract_template_ids": [
                int(item.id) for item in template.linked_contract_templates if item.id is not None
            ],
            "linked_act_template_ids": [
                int(item.id) for item in template.linked_act_templates if item.id is not None
            ],
        }

    @staticmethod
    def _legacy_template_item(item: dict[str, Any], index: int) -> Optional[dict[str, Any]]:
        template_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip() or template_id
        if not template_id:
            return None
        return {
            "id": template_id,
            "document_template_id": None,
            "name": name,
            "doc_type": "contract",
            "document_role_type": DocumentRoleService.normalize_role_type(item.get("document_role_type")),
            "description": None,
            "base_document_type_label": None,
            "is_default": index == 0,
            "is_active": True,
            "is_open_contract": DocumentTemplateService._normalize_bool(item.get("is_open_contract")),
            "client_restricted": False,
            "sort_order": index * 10,
            "customer_ids": [],
            "linked_contract_template_ids": [],
            "linked_act_template_ids": [],
        }

    @staticmethod
    async def legacy_contract_templates(session: AsyncSession) -> list[dict[str, Any]]:
        query = select(GlobalConfig).where(GlobalConfig.key == "contract_templates")
        result = await session.execute(query)
        config = result.scalars().first()
        if not config or not config.value:
            return []
        try:
            raw_items = json.loads(config.value)
        except Exception:
            return []
        if not isinstance(raw_items, list):
            return []
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_items):
            if not isinstance(raw, dict):
                continue
            item = DocumentTemplateService._legacy_template_item(raw, index)
            if not item or item["id"] in seen:
                continue
            seen.add(item["id"])
            items.append(item)
        return items

    @staticmethod
    async def list_templates(session: AsyncSession, doc_type: Optional[str] = None) -> list[DocumentTemplate]:
        stmt = select(DocumentTemplate).options(
            selectinload(DocumentTemplate.customers),
            selectinload(DocumentTemplate.linked_contract_templates),
            selectinload(DocumentTemplate.linked_act_templates),
        )
        if doc_type:
            stmt = stmt.where(DocumentTemplate.doc_type == DocumentTemplateService._normalize_doc_type(doc_type))
        stmt = stmt.order_by(DocumentTemplate.doc_type, DocumentTemplate.sort_order, DocumentTemplate.name)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_template_items(
        session: AsyncSession,
        doc_type: Optional[str] = None,
        *,
        include_legacy: bool = True,
    ) -> list[dict[str, Any]]:
        items = [
            DocumentTemplateService._serialize_template(template)
            for template in await DocumentTemplateService.list_templates(session, doc_type)
        ]
        if include_legacy and (doc_type in {None, "contract"}) and not any(item["doc_type"] == "contract" for item in items):
            items.extend(await DocumentTemplateService.legacy_contract_templates(session))
        return items

    @staticmethod
    async def _load_customers(session: AsyncSession, customer_ids: Iterable[int]) -> list[Customer]:
        ids = []
        for customer_id in customer_ids:
            try:
                normalized_id = int(customer_id)
            except (TypeError, ValueError):
                continue
            if normalized_id > 0:
                ids.append(normalized_id)
        if not ids:
            return []
        result = await session.execute(select(Customer).where(Customer.id.in_(ids)))
        customers = list(result.scalars().all())
        if len(customers) != len(set(ids)):
            raise ValueError("One or more customers were not found")
        return customers

    @staticmethod
    async def _load_templates(
        session: AsyncSession,
        template_ids: Iterable[int],
        *,
        expected_doc_type: str | set[str],
    ) -> list[DocumentTemplate]:
        ids = []
        for template_id in template_ids:
            try:
                normalized_id = int(template_id)
            except (TypeError, ValueError):
                continue
            if normalized_id > 0:
                ids.append(normalized_id)
        if not ids:
            return []
        result = await session.execute(select(DocumentTemplate).where(DocumentTemplate.id.in_(ids)))
        templates = list(result.scalars().all())
        if len(templates) != len(set(ids)):
            raise ValueError("One or more linked templates were not found")
        allowed_types = expected_doc_type if isinstance(expected_doc_type, set) else {expected_doc_type}
        wrong = [template for template in templates if template.doc_type not in allowed_types]
        if wrong:
            raise ValueError(f"Linked templates must have type {', '.join(sorted(allowed_types))}")
        return templates

    @staticmethod
    async def _apply_payload(
        session: AsyncSession,
        template: DocumentTemplate,
        payload: Any,
        *,
        replace_missing: bool,
    ) -> None:
        fields_set = getattr(payload, "model_fields_set", set())

        def should_set(name: str) -> bool:
            return replace_missing or name in fields_set

        if should_set("name"):
            name = " ".join(str(payload.name or "").split())
            if not name:
                raise ValueError("Template name is required")
            template.name = name
        if should_set("doc_type"):
            template.doc_type = DocumentTemplateService._normalize_doc_type(payload.doc_type)
        if should_set("google_template_id"):
            google_template_id = str(payload.google_template_id or "").strip()
            if not google_template_id:
                raise ValueError("Google template ID is required")
            template.google_template_id = google_template_id
        if should_set("document_role_type"):
            template.document_role_type = DocumentRoleService.normalize_role_type(payload.document_role_type)
        if should_set("description"):
            template.description = str(payload.description or "").strip() or None
        if should_set("base_document_type_label"):
            template.base_document_type_label = str(payload.base_document_type_label or "").strip() or None
        if should_set("is_default"):
            template.is_default = bool(payload.is_default)
        if should_set("is_active"):
            template.is_active = bool(payload.is_active)
        if should_set("is_open_contract"):
            template.is_open_contract = bool(payload.is_open_contract)
        if should_set("client_restricted"):
            template.client_restricted = bool(payload.client_restricted)
        if should_set("sort_order"):
            template.sort_order = int(payload.sort_order or 0)
        if should_set("customer_ids"):
            template.customers = await DocumentTemplateService._load_customers(session, payload.customer_ids or [])
        if should_set("linked_act_template_ids"):
            template.linked_act_templates = await DocumentTemplateService._load_templates(
                session,
                payload.linked_act_template_ids or [],
                expected_doc_type="act",
            )
        if should_set("linked_contract_template_ids"):
            template.linked_contract_templates = await DocumentTemplateService._load_templates(
                session,
                payload.linked_contract_template_ids or [],
                expected_doc_type={"contract", "invoice"},
            )

        if template.doc_type == "act":
            template.client_restricted = bool(template.client_restricted)
        elif template.doc_type in {"contract", "invoice"}:
            template.linked_contract_templates = []
        else:
            template.linked_contract_templates = []
            template.linked_act_templates = []

    @staticmethod
    async def create_template(session: AsyncSession, payload: Any) -> dict[str, Any]:
        template = DocumentTemplate(name="", doc_type="contract", google_template_id="")
        await DocumentTemplateService._apply_payload(session, template, payload, replace_missing=True)
        session.add(template)
        await session.commit()
        await session.refresh(template)
        return DocumentTemplateService._serialize_template(
            (await DocumentTemplateService.get_template(session, int(template.id)))
        )

    @staticmethod
    async def get_template(session: AsyncSession, template_id: int) -> DocumentTemplate:
        stmt = (
            select(DocumentTemplate)
            .where(DocumentTemplate.id == template_id)
            .options(
                selectinload(DocumentTemplate.customers),
                selectinload(DocumentTemplate.linked_contract_templates),
                selectinload(DocumentTemplate.linked_act_templates),
            )
        )
        result = await session.execute(stmt)
        template = result.scalars().first()
        if not template:
            raise ValueError("Document template not found")
        return template

    @staticmethod
    async def update_template(session: AsyncSession, template_id: int, payload: Any) -> dict[str, Any]:
        template = await DocumentTemplateService.get_template(session, template_id)
        await DocumentTemplateService._apply_payload(session, template, payload, replace_missing=False)
        session.add(template)
        await session.commit()
        return DocumentTemplateService._serialize_template(await DocumentTemplateService.get_template(session, template_id))

    @staticmethod
    async def delete_template(session: AsyncSession, template_id: int) -> None:
        template = await DocumentTemplateService.get_template(session, template_id)
        await session.execute(
            delete(DocumentTemplateActLink).where(
                (DocumentTemplateActLink.contract_template_id == template_id)
                | (DocumentTemplateActLink.act_template_id == template_id)
            )
        )
        await session.execute(delete(DocumentTemplateCustomerLink).where(DocumentTemplateCustomerLink.template_id == template_id))
        await session.delete(template)
        await session.commit()

    @staticmethod
    async def get_relevant_templates_for_order(
        session: AsyncSession,
        order_id: int,
        doc_type: str,
    ) -> list[dict[str, Any]]:
        order = await session.get(Order, order_id)
        if not order:
            raise ValueError("Order not found")
        return await DocumentTemplateService.get_relevant_templates(
            session,
            doc_type,
            customer_id=order.customer_id,
        )

    @staticmethod
    async def get_relevant_templates(
        session: AsyncSession,
        doc_type: str,
        *,
        customer_id: Optional[int] = None,
        contract_template_id: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        normalized_doc_type = DocumentTemplateService._normalize_doc_type(doc_type)
        templates = await DocumentTemplateService.list_templates(session, normalized_doc_type)
        result: list[DocumentTemplate] = []
        for template in templates:
            if not template.is_active:
                continue
            customer_ids = {customer.id for customer in template.customers}
            if template.client_restricted and customer_id not in customer_ids:
                continue
            if customer_ids and customer_id not in customer_ids and template.client_restricted:
                continue
            if normalized_doc_type in {"contract", "invoice", "retail_receipt", "service_act", "maintenance_service_act", "warranty_certificate"}:
                result.append(template)
                continue
            if contract_template_id:
                contract_ids = {contract.id for contract in template.linked_contract_templates}
                if contract_ids and contract_template_id not in contract_ids:
                    continue
                if not contract_ids and not template.is_default:
                    continue
            result.append(template)

        items = [DocumentTemplateService._serialize_template(template) for template in result]
        if not items and normalized_doc_type == "contract":
            items.extend(await DocumentTemplateService.legacy_contract_templates(session))
        if not items:
            default_id = TEMPLATES.get(normalized_doc_type)
            if default_id:
                default_name = DOC_NAMES.get(normalized_doc_type, normalized_doc_type)
                items.append(
                    {
                        "id": default_id,
                        "document_template_id": None,
                        "name": f"{default_name} (по умолчанию)",
                        "doc_type": normalized_doc_type,
                        "document_role_type": DocumentRoleService.normalize_role_type(None),
                        "description": None,
                        "base_document_type_label": None,
                        "is_default": True,
                        "is_active": True,
                        "is_open_contract": False,
                        "client_restricted": False,
                        "sort_order": 0,
                        "customer_ids": [],
                        "linked_contract_template_ids": [],
                        "linked_act_template_ids": [],
                    }
                )
        return sorted(items, key=lambda item: (not item.get("is_default", False), item.get("sort_order", 0), item["name"]))

    @staticmethod
    async def resolve_template_for_generation(
        session: AsyncSession,
        *,
        order_id: int,
        doc_type: str,
        document_template_id: Optional[int] = None,
        template_id: Optional[str] = None,
        base_document_id: Optional[int] = None,
    ) -> tuple[Optional[int], str]:
        normalized_doc_type = str(doc_type or "").strip()
        if normalized_doc_type not in DocumentTemplateService.MANAGED_TYPES:
            return None, template_id or TEMPLATES.get(normalized_doc_type)

        if document_template_id:
            template = await DocumentTemplateService.get_template(session, document_template_id)
            if template.doc_type != normalized_doc_type:
                raise ValueError("Document template type does not match requested document type")
            if not template.is_active:
                raise ValueError("Document template is inactive")
            return int(template.id), template.google_template_id

        if template_id:
            return None, template_id

        if normalized_doc_type == "act":
            base_doc = await session.get(OrderDocument, base_document_id) if base_document_id else None
            if base_doc and base_doc.order_id != order_id:
                base_doc = None
            if not base_doc:
                base_doc = await DocumentTemplateService._latest_order_document(session, order_id, {"contract", "invoice"})
            contract_template_id = base_doc.document_template_id if base_doc else None
            order = await session.get(Order, order_id)
            relevant = await DocumentTemplateService.get_relevant_templates(
                session,
                "act",
                customer_id=order.customer_id if order else None,
                contract_template_id=contract_template_id,
            )
            managed = next(
                (
                    item
                    for item in relevant
                    if item.get("document_template_id")
                    and contract_template_id
                    and contract_template_id in (item.get("linked_contract_template_ids") or [])
                ),
                None,
            )
            if not managed:
                managed = next((item for item in relevant if item.get("document_template_id")), None)
            if managed:
                return int(managed["document_template_id"]), str(managed["id"])

        relevant = await DocumentTemplateService.get_relevant_templates_for_order(session, order_id, normalized_doc_type)
        managed_default = next((item for item in relevant if item.get("document_template_id") and item.get("is_default")), None)
        if managed_default:
            return int(managed_default["document_template_id"]), str(managed_default["id"])
        managed_first = next((item for item in relevant if item.get("document_template_id")), None)
        if managed_first:
            return int(managed_first["document_template_id"]), str(managed_first["id"])
        return None, TEMPLATES.get(normalized_doc_type)

    @staticmethod
    async def _latest_order_document(session: AsyncSession, order_id: int, doc_type: str | set[str]):
        from models import OrderDocument

        doc_type_filter = OrderDocument.doc_type.in_(doc_type) if isinstance(doc_type, set) else OrderDocument.doc_type == doc_type
        result = await session.execute(
            select(OrderDocument)
            .where(OrderDocument.order_id == order_id, doc_type_filter)
            .order_by(OrderDocument.created_at.desc())
        )
        return result.scalars().first()
