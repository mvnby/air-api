import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerContract, CustomerType, GlobalConfig, Order
from services.document_role_service import DocumentRoleService
from services.google_service import get_google_service


OPEN_SERVICE_CONTRACT_TEMPLATE_ID = "1x-pL1j9g-NzLSpPTLVYXSsmutGExPgfDqzi2VLq9thI"


class CustomerContractService:
    ACTIVE_STATUS = "active"
    ARCHIVED_STATUS = "archived"

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
    def _to_item(contract: CustomerContract) -> Dict[str, Any]:
        return {
            "id": int(contract.id or 0),
            "customer_id": int(contract.customer_id),
            "number": contract.number,
            "valid_from": contract.valid_from,
            "valid_until": contract.valid_until,
            "status": contract.status,
            "template_id": contract.template_id,
            "document_role_type": DocumentRoleService.normalize_role_type(contract.document_role_type),
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
            "number": contract.number,
            "valid_from": contract.valid_from,
            "valid_until": contract.valid_until,
            "status": contract.status,
            "document_role_type": DocumentRoleService.normalize_role_type(contract.document_role_type),
            "edit_url": contract.google_edit_url,
        }

    @staticmethod
    def _build_replacements(customer: Customer, contract: CustomerContract) -> Dict[str, str]:
        client_name = customer.full_legal_name if customer.type == CustomerType.company and customer.full_legal_name else customer.name
        return {
            "{{client_name}}": client_name or "Клиент",
            "{{phone}}": f"Тел: {customer.phone or ''}",
            "{{email}}": f"email: {customer.email or '-'}",
            "{{inn}}": customer.inn or "-",
            "{{address}}": customer.legal_address or customer.actual_address or "-",
            "{{signer_position}}": customer.signer_position or "директора",
            "{{signer_name}}": customer.signer_name or "_______________________________________",
            "{{acting_basis}}": customer.acting_basis or "Устава",
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
    async def list_for_customer(session: AsyncSession, customer_id: int) -> Optional[Dict[str, Any]]:
        customer = await session.get(Customer, customer_id)
        if not customer:
            return None

        result = await session.execute(
            select(CustomerContract)
            .where(CustomerContract.customer_id == customer_id)
            .order_by(CustomerContract.status.asc(), CustomerContract.valid_until.desc(), CustomerContract.id.desc())
        )
        return {"items": [CustomerContractService._to_item(contract) for contract in result.scalars().all()]}

    @staticmethod
    async def _get_next_number(session: AsyncSession, contract_date: datetime) -> str:
        year = contract_date.year
        result = await session.execute(
            select(CustomerContract)
            .where(CustomerContract.number.contains(str(year)))
            .order_by(CustomerContract.id.desc())
        )
        last = result.scalars().first()
        next_num = 1
        if last:
            try:
                next_num = int(str(last.number).split("-")[-1]) + 1
            except (TypeError, ValueError, IndexError):
                next_num = 1
        return f"ОД-{year}-{next_num:03d}"

    @staticmethod
    async def _get_template_role_type(session: AsyncSession, template_id: Optional[str]) -> str:
        if not template_id:
            return DocumentRoleService.normalize_role_type(None)
        try:
            result = await session.execute(select(GlobalConfig).where(GlobalConfig.key == "contract_templates"))
            config = result.scalars().first()
            items = json.loads(config.value) if config and config.value else []
        except Exception:
            return DocumentRoleService.normalize_role_type(None)
        if not isinstance(items, list):
            return DocumentRoleService.normalize_role_type(None)
        for item in items:
            if isinstance(item, dict) and str(item.get("id") or "").strip() == template_id:
                return DocumentRoleService.normalize_role_type(item.get("document_role_type"))
        return DocumentRoleService.normalize_role_type(None)

    @staticmethod
    async def create_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        customer = await session.get(Customer, customer_id)
        if not customer:
            return None
        if customer.type != CustomerType.company:
            raise ValueError("Открытые договоры доступны только для юрлиц")

        contract_date = CustomerContractService._normalize_naive_datetime(payload.get("contract_date")) or datetime.now()
        valid_until = CustomerContractService._normalize_naive_datetime(payload.get("valid_until")) or CustomerContractService._default_valid_until(contract_date)
        number = str(payload.get("number") or "").strip() or await CustomerContractService._get_next_number(session, contract_date)
        template_id = str(payload.get("template_id") or "").strip() or OPEN_SERVICE_CONTRACT_TEMPLATE_ID
        document_role_type = DocumentRoleService.normalize_role_type(
            payload.get("document_role_type") or await CustomerContractService._get_template_role_type(session, template_id)
        )

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
        return CustomerContractService._to_item(contract)

    @staticmethod
    async def upload_for_customer(
        session: AsyncSession,
        *,
        customer_id: int,
        number: str,
        contract_date: datetime,
        valid_until: datetime,
        document_role_type: Optional[str] = None,
        file: "Any",
    ) -> Optional[Dict[str, Any]]:
        import os
        import tempfile

        customer = await session.get(Customer, customer_id)
        if not customer:
            return None
        if customer.type != CustomerType.company:
            raise ValueError("Открытые договоры доступны только для юрлиц")

        cleaned_number = str(number or "").strip()
        if not cleaned_number:
            raise ValueError("Номер договора обязателен")

        valid_from = CustomerContractService._normalize_naive_datetime(contract_date) or datetime.now()
        valid_until_value = CustomerContractService._normalize_naive_datetime(valid_until)
        if not valid_until_value:
            raise ValueError("Дата окончания договора обязательна")

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
                template_id=None,
                document_role_type=DocumentRoleService.normalize_role_type(document_role_type),
                google_file_id=file_id,
                google_edit_url=f"https://drive.google.com/file/d/{file_id}/view?usp=sharing",
            )
            session.add(contract)
            await session.commit()
            await session.refresh(contract)
            return CustomerContractService._to_item(contract)
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
    ) -> Optional[Dict[str, Any]]:
        contract = await session.get(CustomerContract, contract_id)
        if not contract or int(contract.customer_id) != int(customer_id):
            return None

        if "number" in payload and payload.get("number") is not None:
            number = str(payload.get("number") or "").strip()
            if not number:
                raise ValueError("Номер договора обязателен")
            contract.number = number
        if "template_id" in payload:
            template_id = str(payload.get("template_id") or "").strip()
            contract.template_id = template_id or None
        if "document_role_type" in payload:
            contract.document_role_type = DocumentRoleService.normalize_role_type(payload.get("document_role_type"))
        if "contract_date" in payload and payload.get("contract_date") is not None:
            contract.valid_from = CustomerContractService._normalize_naive_datetime(payload.get("contract_date"))
        if "valid_until" in payload and payload.get("valid_until") is not None:
            contract.valid_until = CustomerContractService._normalize_naive_datetime(payload.get("valid_until"))
        if "status" in payload and payload.get("status") is not None:
            status = str(payload.get("status") or "").strip()
            if status not in {CustomerContractService.ACTIVE_STATUS, CustomerContractService.ARCHIVED_STATUS}:
                raise ValueError("Некорректный статус договора")
            contract.status = status

        if contract.google_file_id and any(field in payload for field in {"number", "contract_date", "valid_until", "document_role_type"}):
            customer = await session.get(Customer, customer_id)
            if customer:
                get_google_service().replace_placeholders(
                    contract.google_file_id,
                    CustomerContractService._build_replacements(customer, contract),
                )

        session.add(contract)
        await session.commit()
        await session.refresh(contract)
        return CustomerContractService._to_item(contract)

    @staticmethod
    async def archive_for_customer(session: AsyncSession, *, customer_id: int, contract_id: int) -> Optional[bool]:
        data = await CustomerContractService.update_for_customer(
            session=session,
            customer_id=customer_id,
            contract_id=contract_id,
            payload={"status": CustomerContractService.ARCHIVED_STATUS},
        )
        return None if data is None else True

    @staticmethod
    async def delete_for_customer(session: AsyncSession, *, customer_id: int, contract_id: int) -> Optional[bool]:
        contract = await session.get(CustomerContract, contract_id)
        if not contract or int(contract.customer_id) != int(customer_id):
            return None

        if contract.google_file_id:
            try:
                get_google_service().delete_file(contract.google_file_id)
            except Exception as exc:
                print(f"Error deleting customer contract file from Drive: {exc}")

        await session.execute(
            update(Order)
            .where(Order.customer_contract_id == contract_id)
            .values(customer_contract_id=None)
        )
        await session.delete(contract)
        await session.commit()
        return True
