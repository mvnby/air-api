"""One printed sequence per customer contract shared by Google and CRM."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import CustomerContract, Order, OrderDocument
from services.customer_reconciliation_legacy_review import (
    LEGACY_META_KEY, LegacyDocumentReviewError, read_open_contract_act_number,
)
from services.customer_reconciliation_projection import document_identity

from .errors import ManagedDocumentConflictError


class ContractActNumberConfirmationRequired(ManagedDocumentConflictError):
    def __init__(self, previous: OrderDocument, *, minimum: int):
        message = "Сверьте последний порядковый номер акта по договору с оригиналом."
        if minimum:
            message += f" Уже использован номер {minimum}."
        super().__init__(message)
        file_id = previous.google_file_id or ""
        url = None
        if previous.status is not None:
            url = f"/manager/orders/kanban?orderId={previous.order_id}"
        elif re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
            url = f"https://drive.google.com/open?id={file_id}"
        self.minimum = minimum
        self.previous_act = {
            "id": previous.id, "order_id": previous.order_id,
            "number": (previous.render_snapshot or {}).get("values", {}).get("document.official_full_number") or previous.number,
            "url": url,
        }


def _act_history(contract: CustomerContract):
    return (
        select(OrderDocument, Order.storefront_id)
        .join(Order, Order.id == OrderDocument.order_id)
        .where(
            Order.customer_id == contract.customer_id,
            OrderDocument.doc_type == "act",
            or_(
                OrderDocument.status.is_(None),
                OrderDocument.official_number.is_not(None),
                OrderDocument.status.in_(("issued", "sent", "signed", "replaced")),
            ),
            or_(
                OrderDocument.base_customer_contract_id == contract.id,
                and_(
                    OrderDocument.base_customer_contract_id.is_(None),
                    OrderDocument.base_document_id.is_(None),
                    Order.customer_contract_id == contract.id,
                ),
            ),
        )
    )


def _confirmed_printed_number(document: OrderDocument, contract_id: int) -> int | None:
    identity = document_identity(document)
    if identity["identity_source"] != "confirmed_legacy" or identity["contract_id"] != contract_id:
        return None
    number = str(identity["number"])
    return int(number) if re.fullmatch(r"[1-9][0-9]{0,8}", number) else None


async def _legacy_floor(session: AsyncSession, history, previous: OrderDocument, contract: CustomerContract, old_native):
    # Existing Google issuance may have no readable original. Preserve its old
    # sequence in that case, but flag the series for explicit review on CRM adoption.
    if not old_native and previous.status is None:
        try:
            return await read_open_contract_act_number(previous.google_file_id, contract.number)
        except LegacyDocumentReviewError:
            pass
    contract.act_number_confirmation_pending = True
    return int(await session.scalar(select(func.count()).select_from(history.subquery())))


async def allocate_contract_act_number(
    session: AsyncSession,
    *,
    contract_id: int,
    issuing_document: OrderDocument | None = None,
    confirmed_by: str | None = None,
    storefront_id: int | None = None,
    confirmed_previous_act_number: int | None = None,
    expected_previous_act_id: int | None = None,
) -> int:
    """Advance the counter in the document's transaction; only legacy omits issuing_document."""
    contract = (await session.execute(
        select(CustomerContract).where(CustomerContract.id == contract_id)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one()
    if contract.last_act_number is not None and (
        not contract.act_number_confirmation_pending or issuing_document is None
    ):
        contract.last_act_number += 1
        return contract.last_act_number

    history = _act_history(contract)
    latest = (await session.execute(history.order_by(OrderDocument.id.desc()).limit(1))).first()
    if latest is None:
        if contract.act_number_confirmation_pending:
            raise ManagedDocumentConflictError(
                "Последний акт для сверки недоступен. Восстановите его историю перед выпуском."
            )
        contract.last_act_number = 1
        return 1

    previous, previous_storefront = latest
    # A reviewed number can exceed both the row count and the number in the
    # most recently created act (backdated or reordered documents).
    evidence = await session.scalars(history.where(
        OrderDocument.status.is_(None),
        OrderDocument.scope_meta[LEGACY_META_KEY].as_string().is_not(None),
    ))
    minimum = max(
        (contract.last_act_number or 0),
        max((_confirmed_printed_number(doc, contract_id) or 0 for doc in evidence), default=0),
    )
    old_native = await session.scalar(
        history.with_only_columns(OrderDocument.id)
        .where(OrderDocument.status.is_not(None), OrderDocument.contract_act_number.is_(None)).limit(1)
    )
    # Earlier native templates could use either the annual identifier or an
    # ordinal. Their last paper number cannot be inferred from the row count.
    floor = None if old_native or contract.act_number_confirmation_pending else _confirmed_printed_number(previous, contract_id)
    if floor is None and issuing_document is None:
        floor = await _legacy_floor(session, history, previous, contract, old_native)
    if floor is None:
        if previous_storefront != storefront_id:
            raise ManagedDocumentConflictError(
                "Последний акт договора находится на другой витрине. Сверьте его в карточке клиента."
            )
        if (confirmed_previous_act_number is None or expected_previous_act_id != previous.id
                or not minimum <= confirmed_previous_act_number <= 999_999_999):
            raise ContractActNumberConfirmationRequired(previous, minimum=minimum)
        floor = confirmed_previous_act_number
        issuing_document.scope_meta = {
            **(issuing_document.scope_meta or {}),
            "contract_act_number_confirmation": {
                "previous_act_id": previous.id,
                "previous_act_number": floor,
                "confirmed_by": confirmed_by,
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
            },
        }
        contract.act_number_confirmation_pending = False

    contract.last_act_number = max(floor, minimum) + 1
    return contract.last_act_number
