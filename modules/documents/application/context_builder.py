from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from num2words import num2words
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import (
    CustomerContract,
    DocumentLegalEntity,
    Order,
    OrderDocument,
    OrderProductLink,
    OrderServiceLink,
)
from models.tenancy import TenantScope

from .logistics_rows import build_logistics_rows


class DocumentContextError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentContextSelection:
    order_id: int
    document_type: str
    legal_entity_id: int
    issue_date: date
    proposal_id: int | None = None
    base_document_id: int | None = None
    base_customer_contract_id: int | None = None
    scope_customer_branch_id: int | None = None
    scope_title: str | None = None
    scope_address: str | None = None
    scope_service_line_ids: tuple[int, ...] = ()
    scope_service_line_quantities: Mapping[int, int] | None = None
    scope_product_line_ids: tuple[int, ...] = ()
    business_role: str | None = None


class DocumentContextBuilder:
    """Build a JSON-safe immutable source snapshot without mutating ORM state."""

    SNAPSHOT_VERSION = 1
    NATIVE_TYPES = frozenset({"offer", "invoice", "contract", "act", "tn2", "ttn1"})
    BASE_TYPES = frozenset({"offer", "invoice", "contract"})
    CLOSING_TYPES = frozenset({"act", "tn2", "ttn1"})

    @classmethod
    async def build(
        cls,
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        selection: DocumentContextSelection,
    ) -> dict[str, Any]:
        document_type = str(selection.document_type or "").strip().lower()
        if document_type not in cls.NATIVE_TYPES:
            raise DocumentContextError(
                "Тип документа пока не поддерживается нативным генератором"
            )
        business_role = cls._business_role(document_type, selection.business_role)
        order = await cls._load_order(
            session,
            order_id=selection.order_id,
            tenant_scope=tenant_scope,
        )
        if order is None:
            raise DocumentContextError("Заказ не найден")
        legal_entity = await session.get(DocumentLegalEntity, selection.legal_entity_id)
        if (
            legal_entity is None
            or legal_entity.tenant_id != tenant_scope.tenant_id
            or legal_entity.status != "active"
        ):
            raise DocumentContextError("Активное юридическое лицо не найдено")

        proposal_id, product_links, service_links = cls._select_proposal_lines(
            order,
            selection.proposal_id,
        )
        product_links, service_lines = cls._apply_line_scope(
            product_links,
            service_links,
            document_type=document_type,
            service_ids=selection.scope_service_line_ids,
            service_quantities=selection.scope_service_line_quantities or {},
            product_ids=selection.scope_product_line_ids,
        )
        base_document, base_contract = await cls._resolve_basis(
            session,
            order=order,
            document_type=document_type,
            base_document_id=selection.base_document_id,
            base_customer_contract_id=selection.base_customer_contract_id,
        )
        if (
            document_type in cls.CLOSING_TYPES
            and base_document is None
            and base_contract is None
        ):
            raise DocumentContextError(
                "Для закрывающего документа нужен договор или акцептованный счет-оферта"
            )

        rows = (
            build_logistics_rows(product_links)
            if document_type in {"tn2", "ttn1"}
            else cls._line_rows(product_links, service_lines)
        )
        vat_label = "с НДС" if legal_entity.is_vat_payer else "без НДС"
        for row in rows:
            row["line.vat_label"] = vat_label
        total = sum(
            (Decimal(row["line.amount_raw"]) for row in rows),
            Decimal("0"),
        )
        total_quantity = sum(
            (
                Decimal(row.get("line.quantity_raw", row["line.quantity"]))
                for row in rows
            ),
            Decimal("0"),
        )
        total_weight = sum(
            (Decimal(row.get("line.mass_raw", "0")) for row in rows),
            Decimal("0"),
        )
        issue_date = selection.issue_date
        customer = order.customer
        branch = order.customer_branch
        scope_title = (
            str(selection.scope_title or "").strip()
            or str(getattr(branch, "name", "") or "").strip()
        )
        scope_address = (
            str(selection.scope_address or "").strip()
            or str(
                order.delivery_address or getattr(branch, "delivery_address", "") or ""
            ).strip()
        )
        basis_type, basis_number, basis_date = cls._basis_values(
            base_document,
            base_contract,
        )
        proposal = next(
            (item for item in order.proposals if item.id == proposal_id),
            None,
        )

        values: dict[str, str] = {
            "document.internal_reference": "",
            "document.official_series": "",
            "document.official_number": "",
            "document.official_full_number": "",
            "document.issued_on": issue_date.strftime("%d.%m.%Y"),
            "document.type": document_type,
            "document.business_role": business_role or "",
            "document.act_sequence_number": "",
            "transport.car_model": "—",
            "transport.car_number": "—",
            "transport.driver_name": "—",
            "transport.carrier": "—",
            "basis.type": basis_type,
            "basis.number": basis_number,
            "basis.date": basis_date,
            "seller.display_name": legal_entity.display_name,
            "seller.legal_name": legal_entity.legal_name or legal_entity.display_name,
            "seller.unp": legal_entity.unp or "",
            "seller.is_vat_payer": "Да" if legal_entity.is_vat_payer else "Нет",
            "customer.display_name": str(getattr(customer, "name", "") or ""),
            "customer.full_name": str(
                getattr(customer, "full_legal_name", "")
                or getattr(customer, "name", "")
                or ""
            ),
            "customer.phone": str(getattr(customer, "phone", "") or ""),
            "customer.email": str(getattr(customer, "email", "") or ""),
            "customer.unp": str(getattr(customer, "inn", "") or ""),
            "customer.legal_address": str(
                getattr(customer, "legal_address", "")
                or getattr(customer, "actual_address", "")
                or ""
            ),
            "customer.bank_name": str(getattr(customer, "bank_name", "") or ""),
            "customer.iban": str(getattr(customer, "iban", "") or ""),
            "customer.bic": str(getattr(customer, "bic", "") or ""),
            "customer.signer_position": str(
                getattr(customer, "signer_position", "") or "директора"
            ),
            "customer.signer_name": str(getattr(customer, "signer_name", "") or ""),
            "customer.acting_basis": str(
                getattr(customer, "acting_basis", "") or "Устава"
            ),
            "order.id": str(order.id),
            "order.title": str(order.title or ""),
            "order.object_title": scope_title,
            "order.object_address": scope_address,
            "proposal.name": str(getattr(proposal, "name", "") or ""),
            "totals.amount": cls._money(total),
            "totals.amount_in_words": cls._amount_in_words(total),
            "totals.currency": "BYN",
            "totals.vat_label": vat_label,
            "totals.quantity": cls._quantity(total_quantity),
            "totals.quantity_in_words": num2words(total_quantity, lang="ru"),
            "totals.weight": cls._quantity(total_weight),
            "totals.weight_in_words": num2words(total_weight, lang="ru"),
        }
        for key, value in (legal_entity.requisites or {}).items():
            normalized_key = str(key or "").strip().lower()
            if normalized_key and normalized_key.replace("_", "").isalnum():
                values[f"seller.{normalized_key}"] = str(value or "")

        public_rows = [
            {key: value for key, value in row.items() if not key.endswith("_raw")}
            for row in rows
        ]
        return {
            "schema_version": cls.SNAPSHOT_VERSION,
            "meta": {
                "tenant_id": tenant_scope.tenant_id,
                "order_id": int(order.id),
                "legal_entity_id": int(legal_entity.id),
                "document_type": document_type,
                "proposal_id": proposal_id,
                "base_document_id": int(base_document.id) if base_document else None,
                "base_customer_contract_id": int(base_contract.id)
                if base_contract
                else None,
                "business_role": business_role,
            },
            "values": values,
            "table_rows": {"lines": public_rows},
        }

    @staticmethod
    async def _load_order(
        session: AsyncSession,
        *,
        order_id: int,
        tenant_scope: TenantScope,
    ) -> Order | None:
        result = await session.execute(
            select(Order)
            .where(
                Order.id == order_id,
                Order.tenant_id == tenant_scope.tenant_id,
                Order.storefront_id == tenant_scope.storefront_id,
            )
            .options(
                selectinload(Order.customer),
                selectinload(Order.customer_branch),
                selectinload(Order.customer_contract),
                selectinload(Order.proposals),
                selectinload(Order.product_links).selectinload(
                    OrderProductLink.product
                ),
                selectinload(Order.service_links).selectinload(
                    OrderServiceLink.service
                ),
            )
        )
        return result.unique().scalar_one_or_none()

    @classmethod
    def _select_proposal_lines(
        cls,
        order: Order,
        requested_proposal_id: int | None,
    ) -> tuple[int | None, list[OrderProductLink], list[OrderServiceLink]]:
        active = [item for item in order.proposals if not item.is_archived]
        proposal = None
        if requested_proposal_id is not None:
            proposal = next(
                (item for item in active if item.id == requested_proposal_id),
                None,
            )
            if proposal is None:
                raise DocumentContextError("Предложение заказа не найдено")
        elif active:
            proposal = next((item for item in active if item.is_selected), None)
            proposal = proposal or min(
                active, key=lambda item: (item.sort_order, item.id or 0)
            )
        if proposal is None or proposal.id is None:
            return None, list(order.product_links), list(order.service_links)
        proposal_id = int(proposal.id)
        return (
            proposal_id,
            [item for item in order.product_links if item.proposal_id == proposal_id],
            [item for item in order.service_links if item.proposal_id == proposal_id],
        )

    @classmethod
    def _apply_line_scope(
        cls,
        product_links: Sequence[OrderProductLink],
        service_links: Sequence[OrderServiceLink],
        *,
        document_type: str,
        service_ids: Iterable[int],
        service_quantities: Mapping[int, int],
        product_ids: Iterable[int],
    ) -> tuple[list[OrderProductLink], list[tuple[OrderServiceLink, int]]]:
        requested_service_ids = {int(value) for value in service_ids}
        requested_product_ids = {int(value) for value in product_ids}
        if document_type == "act" and not requested_product_ids:
            selected_products: list[OrderProductLink] = []
        else:
            selected_products = list(product_links)
        selected_services: list[tuple[OrderServiceLink, int]] = [
            (item, int(item.quantity or 0)) for item in service_links
        ]
        if requested_service_ids:
            by_id = {
                int(item.id): item for item in service_links if item.id is not None
            }
            missing = requested_service_ids - by_id.keys()
            if missing:
                raise DocumentContextError("Выбрана услуга не из текущего предложения")
            selected_services = []
            for item_id in sorted(requested_service_ids):
                item = by_id[item_id]
                quantity = int(service_quantities.get(item_id, item.quantity or 0))
                if quantity <= 0 or quantity > int(item.quantity or 0):
                    raise DocumentContextError(
                        "Некорректное количество услуги в документе"
                    )
                selected_services.append((item, quantity))
        if requested_product_ids:
            by_id = {
                int(item.id): item for item in product_links if item.id is not None
            }
            missing = requested_product_ids - by_id.keys()
            if missing:
                raise DocumentContextError("Выбран товар не из текущего предложения")
            selected_products = [
                by_id[item_id] for item_id in sorted(requested_product_ids)
            ]
        return selected_products, selected_services

    @classmethod
    async def _resolve_basis(
        cls,
        session: AsyncSession,
        *,
        order: Order,
        document_type: str,
        base_document_id: int | None,
        base_customer_contract_id: int | None,
    ) -> tuple[OrderDocument | None, CustomerContract | None]:
        if document_type not in cls.CLOSING_TYPES:
            return None, None
        if base_document_id:
            document = await session.get(OrderDocument, base_document_id)
            if (
                document is None
                or document.order_id != order.id
                or document.doc_type not in cls.BASE_TYPES
                or document.status not in {None, "issued", "sent", "signed"}
            ):
                raise DocumentContextError("Документ-основание не найден в заказе")
            if document.doc_type == "invoice" and document.business_role != "offer":
                raise DocumentContextError(
                    "Обычный счет на оплату не является основанием акта"
                )
            return document, None
        requested_contract_id = base_customer_contract_id or order.customer_contract_id
        if requested_contract_id:
            contract = await session.get(CustomerContract, requested_contract_id)
            if (
                contract is None
                or contract.customer_id != order.customer_id
                or contract.status != "active"
            ):
                raise DocumentContextError("Договор клиента не найден")
            return None, contract

        result = await session.execute(
            select(OrderDocument)
            .where(
                OrderDocument.order_id == order.id,
                OrderDocument.doc_type.in_(("contract", "invoice", "offer")),
                OrderDocument.status.in_(("issued", "sent", "signed"))
                | OrderDocument.status.is_(None),
            )
            .order_by(OrderDocument.created_at.desc(), OrderDocument.id.desc())
        )
        candidates = list(result.scalars().all())
        contract = next(
            (item for item in candidates if item.doc_type == "contract"), None
        )
        if contract:
            return contract, None
        offer_invoice = next(
            (
                item
                for item in candidates
                if item.doc_type == "offer"
                or (item.doc_type == "invoice" and item.business_role == "offer")
            ),
            None,
        )
        return offer_invoice, None

    @staticmethod
    def _basis_values(
        document: OrderDocument | None,
        contract: CustomerContract | None,
    ) -> tuple[str, str, str]:
        if contract is not None:
            return (
                "Договор",
                contract.number,
                contract.valid_from.strftime("%d.%m.%Y") if contract.valid_from else "",
            )
        if document is None:
            return "", "", ""
        labels = {"contract": "Договор", "invoice": "Счет-оферта", "offer": "Оферта"}
        if document.official_number:
            number = f"{document.official_series or ''}{document.official_number}"
        else:
            number = document.number
        raw_date = document.official_date or document.date
        return (
            labels.get(document.doc_type, document.doc_type),
            number,
            raw_date.strftime("%d.%m.%Y"),
        )

    @classmethod
    def _line_rows(
        cls,
        product_links: Sequence[OrderProductLink],
        service_lines: Sequence[tuple[OrderServiceLink, int]],
    ) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for item in product_links:
            quantity = int(item.quantity or 0)
            unit_price = Decimal(str(item.price or 0))
            rows.append(
                cls._line_row(
                    len(rows) + 1,
                    title=str(
                        item.title_snapshot
                        or getattr(item.product, "title", "")
                        or "Товар"
                    ),
                    kind="product",
                    quantity=quantity,
                    unit_price=unit_price,
                )
            )
        for item, quantity in service_lines:
            unit_price = Decimal(str(item.price or 0))
            rows.append(
                cls._line_row(
                    len(rows) + 1,
                    title=str(
                        item.title or getattr(item.service, "title", "") or "Услуга"
                    ),
                    kind="service",
                    quantity=quantity,
                    unit_price=unit_price,
                )
            )
        return rows

    @classmethod
    def _line_row(
        cls,
        index: int,
        *,
        title: str,
        kind: str,
        quantity: int,
        unit_price: Decimal,
    ) -> dict[str, str]:
        amount = unit_price * quantity
        return {
            "line.number": str(index),
            "line.title": title,
            "line.kind": kind,
            "line.unit": "шт.",
            "line.quantity": str(quantity),
            "line.unit_price": cls._money(unit_price),
            "line.amount": cls._money(amount),
            "line.country": "",
            "line.vat_label": "",
            "line.seats": "",
            "line.mass": "",
            "line.note": "",
            "line.amount_raw": str(amount),
            "line.quantity_raw": str(quantity),
            "line.mass_raw": "0",
        }

    @staticmethod
    def _business_role(document_type: str, raw: str | None) -> str | None:
        if document_type != "invoice":
            return None
        normalized = str(raw or "payment_request").strip().lower()
        if normalized not in {"payment_request", "offer"}:
            raise DocumentContextError(
                "Для счета выберите режим оплаты или счета-оферты"
            )
        return normalized

    @staticmethod
    def _money(value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"

    @staticmethod
    def _quantity(value: Decimal) -> str:
        return format(value.normalize(), "f")

    @classmethod
    def _amount_in_words(cls, amount: Decimal) -> str:
        rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rubles = int(rounded)
        kopecks = int((rounded - rubles) * 100)
        ruble_word = cls._plural(
            rubles, "белорусский рубль", "белорусских рубля", "белорусских рублей"
        )
        kopeck_word = cls._plural(kopecks, "копейка", "копейки", "копеек")
        return (
            f"{num2words(rubles, lang='ru')} {ruble_word} {kopecks:02d} {kopeck_word}"
        ).capitalize()

    @staticmethod
    def _plural(value: int, one: str, few: str, many: str) -> str:
        if value % 100 in {11, 12, 13, 14}:
            return many
        if value % 10 == 1:
            return one
        if value % 10 in {2, 3, 4}:
            return few
        return many
