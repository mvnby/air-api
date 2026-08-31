from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Callable

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import (
    DocumentNumberReservation,
    DocumentNumberSequence,
    Order,
    OrderDocument,
)
from modules.documents.domain.numbering import DocumentNumberScope


@dataclass(frozen=True, slots=True)
class DocumentNumberReservationResult:
    reservation_id: str
    number_value: int
    number_text: str
    reused: bool


class DocumentNumberingRepository:
    """Persists an official-number allocation atomically inside one transaction.

    Callers must commit the short reservation transaction before starting file
    rendering. The reservation row is deliberately retained after voiding or
    replacement so an issued number is never returned to the pool.
    """

    _SCOPE_COLUMNS = (
        "tenant_id",
        "legal_entity_id",
        "document_type",
        "series",
        "period_key",
    )

    @classmethod
    async def reserve(
        cls,
        session: AsyncSession,
        *,
        scope: DocumentNumberScope,
        idempotency_key: str,
        minimum_width: int = 3,
        number_text_formatter: Callable[[int], str] | None = None,
        legacy_document_type: str | None = None,
    ) -> DocumentNumberReservationResult:
        normalized_scope = scope.normalized()
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise ValueError("Idempotency key is required")
        if minimum_width <= 0:
            raise ValueError("Minimum width must be positive")

        dialect_name = cls._dialect_name(session)
        await cls._lock_allocation_scope(session, normalized_scope, dialect_name)
        if dialect_name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
                {
                    "lock_key": (
                        f"document_number_idempotency:{normalized_scope.tenant_id}:"
                        f"{normalized_key}"
                    )
                },
            )

        existing = await cls._find_existing(
            session,
            tenant_id=normalized_scope.tenant_id,
            idempotency_key=normalized_key,
        )
        if existing is not None:
            cls._assert_same_scope(existing, normalized_scope)
            return DocumentNumberReservationResult(
                reservation_id=existing.id,
                number_value=existing.number_value,
                number_text=existing.number_text,
                reused=True,
            )

        if legacy_document_type is not None:
            await cls._bootstrap_legacy_sequence(
                session,
                scope=normalized_scope,
                legacy_document_type=legacy_document_type,
            )

        next_value = await cls._increment_sequence(
            session, normalized_scope, dialect_name
        )
        reservation_number_text = (
            number_text_formatter(next_value)
            if number_text_formatter is not None
            else f"{normalized_scope.series}{next_value:0{minimum_width}d}"
        )
        reservation = DocumentNumberReservation(
            tenant_id=normalized_scope.tenant_id,
            legal_entity_id=normalized_scope.legal_entity_id,
            document_type=normalized_scope.document_type,
            series=normalized_scope.series,
            period_key=normalized_scope.period_key,
            number_value=next_value,
            number_text=reservation_number_text,
            idempotency_key=normalized_key,
        )
        session.add(reservation)
        await session.flush()
        return DocumentNumberReservationResult(
            reservation_id=reservation.id,
            number_value=next_value,
            number_text=reservation_number_text,
            reused=False,
        )

    @staticmethod
    async def attach_to_document(
        session: AsyncSession,
        *,
        tenant_id: int,
        reservation_id: str,
        document_id: int,
    ) -> DocumentNumberReservation:
        reservation = (
            await session.execute(
                select(DocumentNumberReservation)
                .where(
                    DocumentNumberReservation.id == reservation_id,
                    DocumentNumberReservation.tenant_id == tenant_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if reservation is None:
            raise ValueError("Document number reservation not found")
        if reservation.document_id not in {None, document_id}:
            raise ValueError("Document number reservation belongs to another document")
        document_legal_entity_id = (
            await session.execute(
                select(OrderDocument.legal_entity_id).where(
                    OrderDocument.id == document_id,
                    OrderDocument.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if document_legal_entity_id != reservation.legal_entity_id:
            raise ValueError(
                "Document number reservation belongs to another legal entity"
            )
        reservation.document_id = document_id
        session.add(reservation)
        await session.flush()
        return reservation

    @staticmethod
    async def mark_assigned(
        session: AsyncSession,
        *,
        tenant_id: int,
        document_id: int,
    ) -> DocumentNumberReservation:
        reservation = (
            await session.execute(
                select(DocumentNumberReservation)
                .where(
                    DocumentNumberReservation.tenant_id == tenant_id,
                    DocumentNumberReservation.document_id == document_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if reservation is None:
            raise ValueError("Document number reservation not found")
        if reservation.status == "void":
            raise ValueError("Voided document number cannot be assigned")
        reservation.status = "assigned"
        reservation.assigned_at = reservation.assigned_at or datetime.now(timezone.utc)
        session.add(reservation)
        await session.flush()
        return reservation

    @staticmethod
    async def mark_void(
        session: AsyncSession,
        *,
        tenant_id: int,
        document_id: int,
    ) -> DocumentNumberReservation | None:
        reservation = (
            await session.execute(
                select(DocumentNumberReservation)
                .where(
                    DocumentNumberReservation.tenant_id == tenant_id,
                    DocumentNumberReservation.document_id == document_id,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if reservation is None:
            return None
        reservation.status = "void"
        session.add(reservation)
        await session.flush()
        return reservation

    @staticmethod
    def _dialect_name(session: AsyncSession) -> str:
        bind = session.get_bind()
        return str(getattr(getattr(bind, "dialect", None), "name", ""))

    @staticmethod
    async def _lock_allocation_scope(
        session: AsyncSession,
        scope: DocumentNumberScope,
        dialect_name: str,
    ) -> None:
        """Serialize bootstrap and allocation for one durable sequence scope."""

        if dialect_name != "postgresql":
            return
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
            {
                "lock_key": (
                    "document_number_allocation:"
                    f"{scope.tenant_id}:{scope.legal_entity_id}:"
                    f"{scope.document_type}:{scope.series}:{scope.period_key}"
                )
            },
        )

    @classmethod
    async def _bootstrap_legacy_sequence(
        cls,
        session: AsyncSession,
        *,
        scope: DocumentNumberScope,
        legacy_document_type: str,
    ) -> None:
        """Lift, never reset, a default issuer's native sequence from legacy rows.

        Legacy OrderDocument rows do not carry a legal entity. The caller opts
        in only for its tenant's default issuer; joining Order keeps another
        tenant's old rows out of the floor calculation.
        """

        normalized_type = str(legacy_document_type or "").strip().lower()
        if not normalized_type or not re.fullmatch(r"\d{4}", scope.period_key):
            return
        pattern = re.compile(
            rf"^{re.escape(scope.series)}{scope.period_key}-(\d+)$"
        )
        legacy_numbers = (
            await session.execute(
                select(OrderDocument.number)
                .join_from(OrderDocument, Order)
                .where(
                    Order.tenant_id == scope.tenant_id,
                    OrderDocument.doc_type == normalized_type,
                    OrderDocument.internal_reference.is_(None),
                )
            )
        ).scalars()
        legacy_floor = max(
            (
                int(match.group(1))
                for number in legacy_numbers
                if (match := pattern.fullmatch(str(number or "").strip()))
            ),
            default=0,
        )
        native_floor = (
            await session.execute(
                select(func.max(DocumentNumberReservation.number_value)).where(
                    DocumentNumberReservation.tenant_id == scope.tenant_id,
                    DocumentNumberReservation.legal_entity_id == scope.legal_entity_id,
                    DocumentNumberReservation.document_type == scope.document_type,
                    DocumentNumberReservation.series == scope.series,
                    DocumentNumberReservation.period_key == scope.period_key,
                )
            )
        ).scalar_one_or_none() or 0
        sequence = (
            await session.execute(
                select(DocumentNumberSequence)
                .where(
                    DocumentNumberSequence.tenant_id == scope.tenant_id,
                    DocumentNumberSequence.legal_entity_id == scope.legal_entity_id,
                    DocumentNumberSequence.document_type == scope.document_type,
                    DocumentNumberSequence.series == scope.series,
                    DocumentNumberSequence.period_key == scope.period_key,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        floor = max(
            legacy_floor,
            int(native_floor),
            int(sequence.last_value or 0) if sequence else 0,
        )
        if sequence is None:
            if floor:
                session.add(
                    DocumentNumberSequence(
                        tenant_id=scope.tenant_id,
                        legal_entity_id=scope.legal_entity_id,
                        document_type=scope.document_type,
                        series=scope.series,
                        period_key=scope.period_key,
                        last_value=floor,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                await session.flush()
            return
        if sequence.last_value < floor:
            sequence.last_value = floor
            sequence.updated_at = datetime.now(timezone.utc)
            session.add(sequence)
            await session.flush()

    @staticmethod
    async def _find_existing(
        session: AsyncSession,
        *,
        tenant_id: int,
        idempotency_key: str,
    ) -> DocumentNumberReservation | None:
        result = await session.execute(
            select(DocumentNumberReservation).where(
                DocumentNumberReservation.tenant_id == tenant_id,
                DocumentNumberReservation.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    async def _increment_sequence(
        cls,
        session: AsyncSession,
        scope: DocumentNumberScope,
        dialect_name: str,
    ) -> int:
        values = {
            "tenant_id": scope.tenant_id,
            "legal_entity_id": scope.legal_entity_id,
            "document_type": scope.document_type,
            "series": scope.series,
            "period_key": scope.period_key,
            "last_value": 1,
            "updated_at": datetime.now(timezone.utc),
        }
        if dialect_name in {"postgresql", "sqlite"}:
            insert_factory = (
                postgresql_insert if dialect_name == "postgresql" else sqlite_insert
            )
            statement = insert_factory(DocumentNumberSequence).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=list(cls._SCOPE_COLUMNS),
                set_={
                    "last_value": DocumentNumberSequence.last_value + 1,
                    "updated_at": values["updated_at"],
                },
            ).returning(DocumentNumberSequence.last_value)
            result = await session.execute(statement)
            return int(result.scalar_one())

        result = await session.execute(
            select(DocumentNumberSequence)
            .where(
                DocumentNumberSequence.tenant_id == scope.tenant_id,
                DocumentNumberSequence.legal_entity_id == scope.legal_entity_id,
                DocumentNumberSequence.document_type == scope.document_type,
                DocumentNumberSequence.series == scope.series,
                DocumentNumberSequence.period_key == scope.period_key,
            )
            .with_for_update()
        )
        sequence = result.scalar_one_or_none()
        if sequence is None:
            sequence = DocumentNumberSequence(**values)
            session.add(sequence)
        else:
            sequence.last_value += 1
            sequence.updated_at = values["updated_at"]
        await session.flush()
        return int(sequence.last_value)

    @staticmethod
    def _assert_same_scope(
        reservation: DocumentNumberReservation,
        scope: DocumentNumberScope,
    ) -> None:
        stored = (
            reservation.legal_entity_id,
            reservation.document_type,
            reservation.series,
            reservation.period_key,
        )
        requested = (
            scope.legal_entity_id,
            scope.document_type,
            scope.series,
            scope.period_key,
        )
        if stored != requested:
            raise ValueError(
                "Idempotency key is already bound to another numbering scope"
            )
