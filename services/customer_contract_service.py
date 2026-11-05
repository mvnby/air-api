import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import String, cast, exists, or_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerContract, DocumentLegalEntity, GlobalConfig, Order, OrderDocument
from models.tenancy import TenantScope
from modules.documents.domain.customer_signing import customer_signing_text
from modules.documents.domain.party import customer_document_entity_type
from services.document_role_service import DocumentRoleService
from services.google_service import get_google_service
from services.customer_reconciliation_legacy_review import LEGACY_META_KEY
from services.customer_party import is_business_customer_type
from services.tenant_scope_service import tenant_scope_clause


OPEN_SERVICE_CONTRACT_TEMPLATE_ID = "1x-pL1j9g-NzLSpPTLVYXSsmutGExPgfDqzi2VLq9thI"


class ContractHistoryConflict(ValueError):
    pass


def contract_has_history():
    confirmed_id = OrderDocument.scope_meta[LEGACY_META_KEY]["contract_id"].as_string()
    confirmed_reference = (
        select(OrderDocument.id).join(Order, Order.id == OrderDocument.order_id)
        .where(Order.customer_id == CustomerContract.customer_id,
               cast(confirmed_id, String) == cast(CustomerContract.id, String))
        .correlate(CustomerContract).exists()
    )
    return or_(
        CustomerContract.last_act_number.is_not(None),
        exists().where(Order.customer_contract_id == CustomerContract.id),
        exists().where(OrderDocument.base_customer_contract_id == CustomerContract.id),
        confirmed_reference,
    )


def _register_items(customer_id: int, tenant_scope: TenantScope):
    visible_order_id = (
        select(OrderDocument.order_id)
        .join(Order, Order.id == OrderDocument.order_id)
        .where(
            OrderDocument.id == CustomerContract.source_document_id,
            OrderDocument.tenant_id == tenant_scope.tenant_id,
            Order.tenant_id == tenant_scope.tenant_id,
            Order.storefront_id == tenant_scope.storefront_id,
            Order.customer_id == customer_id,
        )
        .correlate(CustomerContract).scalar_subquery()
    )
    return select(CustomerContract, contract_has_history(), visible_order_id).where(
        CustomerContract.customer_id == customer_id
    )


class CustomerContractService:
    ACTIVE_STATUS = "active"
    ARCHIVED_STATUS = "archived"

    @staticmethod
    def _is_business_customer(customer: Customer) -> bool:
        return is_business_customer_type(customer.type)

    @staticmethod
    def _normalize_naive_datetime(value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is not None:
            return value.replace(tzinfo=None)
        return value

    @staticmethod
    def _default_valid_until(valid_from: datetime) -> datetime:
        try:
            return valid_from.replace(year=valid_from.year + 1)
        except ValueError:
            return valid_from.replace(month=2, day=28, year=valid_from.year + 1)

    @staticmethod
    def _format_date(value: Optional[datetime]) -> str:
        return value.strftime("%d.%m.%Y") if value else "-"

    @staticmethod
    def _to_item(contract: CustomerContract, *, can_delete: bool = False, source_order_id: int | None = None) -> Dict[str, Any]:
        return {
            "id": int(contract.id or 0),
            "customer_id": int(contract.customer_id),
            "number": contract.number,
            "valid_from": contract.valid_from,
            "valid_until": contract.valid_until,
            "status": contract.status,
            "template_id": contract.template_id,
            "legal_entity_id": contract.legal_entity_id,
            "source_kind": "crm" if contract.source_document_id else "google",
            "source_document_id": contract.source_document_id if source_order_id is not None else None,
            "source_order_id": source_order_id,
            "can_delete": can_delete and contract.source_document_id is None,
            "document_role_type": contract.document_role_type,
            "edit_url": contract.google_edit_url,
            "created_at": contract.created_at,
            "updated_at": contract.updated_at,
        }

    @staticmethod
    def to_order_brief(contract: Optional[CustomerContract]) -> Optional[Dict[str, Any]]:
        if not contract:
            return None
        return {
            "id": int(contract.id or 0),
            "customer_id": int(contract.customer_id),
            "legal_entity_id": contract.legal_entity_id,
            "number": contract.number,
            "valid_from": contract.valid_from,
            "valid_until": contract.valid_until,
            "status": contract.status,
            "document_role_type": contract.document_role_type,
            "edit_url": contract.google_edit_url,
        }

    @staticmethod
    def _build_replacements(customer: Customer, contract: CustomerContract) -> Dict[str, str]:
        is_business = CustomerContractService._is_business_customer(customer)
        signing = customer_signing_text(
            entity_type=customer_document_entity_type(
                customer.type, name=customer.name, full_legal_name=customer.full_legal_name,
            ),
            signing_mode=customer.signing_mode,
            signer_position=customer.signer_position,
            signer_name=customer.signer_name,
            acting_basis=customer.acting_basis,
        )
        client_name = customer.full_legal_name if is_business and customer.full_legal_name else customer.name
        return {
            "{{client_name}}": client_name or "Клиент",
            "{{phone}}": f"Тел: {customer.phone or ''}",
            "{{email}}": f"email: {customer.email or '-'}",
            "{{inn}}": customer.inn or "-",
            "{{address}}": customer.legal_address or customer.actual_address or "-",
            "{{signer_position}}": signing["signer_position"],
            "{{signer_name}}": signing["signer_name"],
            "{{acting_basis}}": signing["acting_basis"],
            "{{bank_name}}": customer.bank_name or "-",
            "{{iban}}": customer.iban or "-",
            "{{bic}}": customer.bic or "-",
            "{{date}}": CustomerContractService._format_date(contract.valid_from),
            "{{contract_name}}": contract.number,
            "{{contract_number}}": contract.number,
            "{{contract_date}}": CustomerContractService._format_date(contract.valid_from),
            "{{contract_valid_from}}": CustomerContractService._format_date(contract.valid_from),
            "{{contract_valid_until}}": CustomerContractService._format_date(contract.valid_until),
            "{{document_role_type}}": DocumentRoleService.normalize_role_type(contract.document_role_type),
        }

    @staticmethod
    async def _get_scoped_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[Customer]:
        return (
            await session.execute(
                select(Customer).where(
                    Customer.id == customer_id,
                    tenant_scope_clause(Customer, tenant_scope),
                )
            )
        ).scalars().first()

    @staticmethod
    async def list_for_customer(
        session: AsyncSession,
        customer_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerContractService._get_scoped_customer(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None

        result = await session.execute(
            _register_items(customer_id, tenant_scope)
            .order_by(CustomerContract.status.asc(), CustomerContract.valid_until.desc(), CustomerContract.id.desc())
        )
        return {"items": [
            CustomerContractService._to_item(contract, can_delete=not used, source_order_id=source_order_id)
            for contract, used, source_order_id in result.all()
        ]}

    @staticmethod
    async def _get_next_number(session: AsyncSession, contract_date: datetime) -> str:
        year = contract_date.year
        bind = session.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", "") == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
                {"lock_key": f"customer_contract_number:ОД-{year}-"},
            )
        prefix = f"ОД-{year}-"
        numbers = await session.scalars(select(CustomerContract.number).where(
            CustomerContract.number.startswith(prefix)
        ))
        suffixes = (number[len(prefix):] for number in numbers)
        last = max((int(value) for value in suffixes if value.isascii() and value.isdigit()), default=0)
        return f"{prefix}{last + 1:03d}"

    @staticmethod
    async def _get_template_role_type(session: AsyncSession, template_id: Optional[str]) -> str:
        template = await CustomerContractService._get_contract_template(session, template_id)
        if template:
            return DocumentRoleService.normalize_role_type(template.get("document_role_type"))
        return DocumentRoleService.normalize_role_type(None)

    @staticmethod
    async def _get_contract_templates(session: AsyncSession) -> list[dict]:
        try:
            result = await session.execute(select(GlobalConfig).where(GlobalConfig.key == "contract_templates"))
            config = result.scalars().first()
            items = json.loads(config.value) if config and config.value else []
        except Exception:
            return []
        if not isinstance(items, list):
            return []

        from services.document_service import DocumentService

        templates = []
        for item in items:
            if not isinstance(item, dict):
                continue
            normalized = DocumentService._normalize_template_item(item)
            if normalized:
                templates.append(normalized)
        return templates

    @staticmethod
    async def _get_contract_template(session: AsyncSession, template_id: Optional[str]) -> Optional[dict]:
        cleaned_id = str(template_id or "").strip()
        if not cleaned_id:
            return None
        templates = await CustomerContractService._get_contract_templates(session)
        return next((template for template in templates if template.get("id") == cleaned_id), None)

    @staticmethod
    async def _resolve_open_contract_template(session: AsyncSession, template_id: Optional[str]) -> dict:
        templates = await CustomerContractService._get_contract_templates(session)
        cleaned_id = str(template_id or "").strip()
        if cleaned_id:
            template = next((item for item in templates if item.get("id") == cleaned_id), None)
            if not template:
                raise ValueError("Шаблон договора не найден")
            if not template.get("is_open_contract"):
                raise ValueError("Выберите шаблон, отмеченный как открытый договор")
            return template

        template = next((item for item in templates if item.get("is_open_contract")), None)
        if not template:
            raise ValueError("В настройках нет шаблонов, отмеченных как открытый договор")
        return template

    @staticmethod
    async def create_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerContractService._get_scoped_customer(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None
        if not CustomerContractService._is_business_customer(customer):
            raise ValueError("Открытые договоры доступны для организаций и ИП")

        contract_date = CustomerContractService._normalize_naive_datetime(payload.get("contract_date")) or datetime.now()
        valid_until = CustomerContractService._normalize_naive_datetime(payload.get("valid_until")) or CustomerContractService._default_valid_until(contract_date)
        number = str(payload.get("number") or "").strip() or await CustomerContractService._get_next_number(session, contract_date)
        template = await CustomerContractService._resolve_open_contract_template(session, payload.get("template_id"))
        template_id = str(template.get("id") or "").strip()
        document_role_type = DocumentRoleService.normalize_role_type(template.get("document_role_type"))

        contract = CustomerContract(
            customer_id=customer_id,
            number=number,
            valid_from=contract_date,
            valid_until=valid_until,
            status=CustomerContractService.ACTIVE_STATUS,
            template_id=template_id,
            document_role_type=document_role_type,
        )

        title = f"Открытый договор {number} {customer.name}"
        file_info = get_google_service().copy_template(template_id, title)
        contract.google_file_id = file_info["file_id"]
        contract.google_edit_url = file_info["edit_url"]
        get_google_service().replace_placeholders(
            contract.google_file_id,
            CustomerContractService._build_replacements(customer, contract),
        )

        session.add(contract)
        await session.commit()
        await session.refresh(contract)
        return CustomerContractService._to_item(contract, can_delete=True)

    @staticmethod
    async def upload_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        number: str,
        contract_date: datetime,
        valid_until: datetime,
        template_id: Optional[str] = None,
        document_role_type: Optional[str] = None,
        file: "Any",
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        import os
        import tempfile

        customer = await CustomerContractService._get_scoped_customer(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if not customer:
            return None
        if not CustomerContractService._is_business_customer(customer):
            raise ValueError("Открытые договоры доступны для организаций и ИП")

        cleaned_number = str(number or "").strip()
        if not cleaned_number:
            raise ValueError("Номер договора обязателен")

        valid_from = CustomerContractService._normalize_naive_datetime(contract_date) or datetime.now()
        valid_until_value = CustomerContractService._normalize_naive_datetime(valid_until)
        if not valid_until_value:
            raise ValueError("Дата окончания договора обязательна")

        template = await CustomerContractService._resolve_open_contract_template(session, template_id)
        resolved_role_type = DocumentRoleService.normalize_role_type(
            document_role_type or template.get("document_role_type")
        )

        original_filename = file.filename or f"open-contract-{cleaned_number}.pdf"
        _, suffix = os.path.splitext(original_filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            from services.google_service import DESTINATION_FOLDER_ID

            title = f"Открытый договор {cleaned_number} {customer.name}{suffix or ''}"
            file_id = get_google_service().upload_file(
                file_path=tmp_path,
                filename=title,
                mime_type=file.content_type or "application/octet-stream",
                folder_id=DESTINATION_FOLDER_ID,
            )
            contract = CustomerContract(
                customer_id=customer_id,
                number=cleaned_number,
                valid_from=valid_from,
                valid_until=valid_until_value,
                status=CustomerContractService.ACTIVE_STATUS,
                template_id=str(template.get("id") or "").strip() or None,
                document_role_type=resolved_role_type,
                google_file_id=file_id,
                google_edit_url=f"https://drive.google.com/file/d/{file_id}/view?usp=sharing",
            )
            session.add(contract)
            await session.commit()
            await session.refresh(contract)
            return CustomerContractService._to_item(contract, can_delete=True)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    @staticmethod
    async def update_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        contract_id: int,
        payload: Dict[str, Any],
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        customer = await CustomerContractService._get_scoped_customer(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if customer is None:
            return None
        contract = await session.scalar(
            select(CustomerContract)
            .where(CustomerContract.id == contract_id, CustomerContract.customer_id == customer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if contract is None:
            return None

        if contract.source_document_id is not None and payload != {"status": "archived"}:
            raise ValueError("Реквизиты договора CRM зафиксированы при выпуске. Для исправления выпустите замену.")
        if "legal_entity_id" in payload:
            issuer = await session.scalar(select(DocumentLegalEntity).where(
                DocumentLegalEntity.id == payload["legal_entity_id"],
                DocumentLegalEntity.tenant_id == tenant_scope.tenant_id,
                DocumentLegalEntity.status == "active",
            ))
            if issuer is None:
                raise ValueError("Выберите действующего исполнителя из этого аккаунта")
            if not DocumentRoleService.nullable_role_type(payload.get("document_role_type")):
                raise ValueError("Сверьте с оригиналом и укажите названия сторон")
            conflicting_issue = await session.scalar(select(exists().where(
                OrderDocument.base_customer_contract_id == contract_id,
                OrderDocument.legal_entity_id != issuer.id,
                OrderDocument.status.in_(("issued", "sent", "signed", "replaced")),
            )))
            if conflicting_issue:
                raise ValueError("По договору уже выпущены документы другого исполнителя. Сверьте историю договора.")
            contract.legal_entity_id = issuer.id

        if "number" in payload and payload.get("number") is not None:
            number = str(payload.get("number") or "").strip()
            if not number:
                raise ValueError("Номер договора обязателен")
            contract.number = number
        if "template_id" in payload:
            template_id = str(payload.get("template_id") or "").strip()
            contract.template_id = template_id or None
        if "document_role_type" in payload:
            contract.document_role_type = DocumentRoleService.nullable_role_type(payload.get("document_role_type"))
        if "contract_date" in payload and payload.get("contract_date") is not None:
            contract.valid_from = CustomerContractService._normalize_naive_datetime(payload.get("contract_date"))
        if "valid_until" in payload and payload.get("valid_until") is not None:
            contract.valid_until = CustomerContractService._normalize_naive_datetime(payload.get("valid_until"))
        if "status" in payload and payload.get("status") is not None:
            status = str(payload.get("status") or "").strip()
            if status not in {CustomerContractService.ACTIVE_STATUS, CustomerContractService.ARCHIVED_STATUS}:
                raise ValueError("Некорректный статус договора")
            contract.status = status

        if contract.google_file_id and any(field in payload for field in {"number", "contract_date", "valid_until"}):
            if customer:
                get_google_service().replace_placeholders(
                    contract.google_file_id,
                    CustomerContractService._build_replacements(customer, contract),
                )

        session.add(contract)
        await session.flush()
        current, used, source_order_id = (await session.execute(
            _register_items(customer_id, tenant_scope).where(CustomerContract.id == contract_id)
        )).one()
        item = CustomerContractService._to_item(current, can_delete=not used, source_order_id=source_order_id)
        await session.commit()
        return item

    @staticmethod
    async def archive_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        contract_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[bool]:
        data = await CustomerContractService.update_for_customer(
            session=session,
            customer_id=customer_id,
            contract_id=contract_id,
            payload={"status": CustomerContractService.ARCHIVED_STATUS},
            tenant_scope=tenant_scope,
        )
        return None if data is None else True

    @staticmethod
    async def delete_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        contract_id: int,
        tenant_scope: TenantScope,
    ) -> Optional[bool]:
        customer = await CustomerContractService._get_scoped_customer(
            session,
            customer_id=customer_id,
            tenant_scope=tenant_scope,
        )
        if customer is None:
            return None
        contract = await session.scalar(
            select(CustomerContract)
            .where(CustomerContract.id == contract_id, CustomerContract.customer_id == customer_id)
            .with_for_update()
        )
        if contract is None:
            return None
        if contract.source_document_id is not None:
            raise ContractHistoryConflict("Договор выпущен в CRM. Для завершения использования архивируйте его.")
        used = await session.scalar(
            select(contract_has_history()).select_from(CustomerContract).where(CustomerContract.id == contract_id)
        )
        if used:
            raise ContractHistoryConflict("По договору есть заказ или документ. Архивируйте договор.")
        file_id = contract.google_file_id
        await session.delete(contract)
        await session.commit()
        if file_id:
            # Drive cleanup follows a successful DB commit; a failed delete keeps the original.
            try:
                await asyncio.to_thread(lambda: get_google_service().delete_file(file_id))
            except Exception:
                logging.getLogger(__name__).exception("Drive cleanup failed for removed customer contract %s", contract_id)
        return True
