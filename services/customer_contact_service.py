from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, CustomerContact, CustomerContactHistory
from models.tenancy import TenantScope
from services.tenant_scope_service import tenant_scope_clause

CONTACT_FIELDS = ("name", "role", "phone", "email", "is_primary", "is_active")


class CustomerContactService:
    @staticmethod
    def _clean(value: Any) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @staticmethod
    def _contact_item(contact: CustomerContact) -> dict[str, Any]:
        return {
            "id": contact.id,
            "customer_id": contact.customer_id,
            "name": contact.name,
            "role": contact.role,
            "phone": contact.phone,
            "email": contact.email,
            "is_primary": bool(contact.is_primary),
            "is_active": bool(contact.is_active),
            "created_at": contact.created_at,
            "updated_at": contact.updated_at,
            "is_legacy": bool(contact.is_legacy),
        }

    @staticmethod
    def _history_item(entry: CustomerContactHistory) -> dict[str, Any]:
        return {
            "id": entry.id,
            "contact_id": entry.contact_id,
            "field_name": entry.field_name,
            "old_value": entry.old_value,
            "new_value": entry.new_value,
            "author_id": entry.author_id,
            "author_name": entry.author_name,
            "changed_at": entry.changed_at,
        }

    @staticmethod
    async def _lock_customer(
        session: AsyncSession, customer_id: int, tenant_scope: TenantScope, *, lock: bool = True
    ) -> Optional[Customer]:
        statement = select(Customer).where(
            Customer.id == customer_id,
            tenant_scope_clause(Customer, tenant_scope),
        )
        if lock:
            statement = statement.with_for_update()
        result = await session.execute(statement)
        return result.scalars().first()

    @staticmethod
    async def _contacts(session: AsyncSession, customer_id: int) -> list[CustomerContact]:
        result = await session.execute(
            select(CustomerContact)
            .where(CustomerContact.customer_id == customer_id)
            .order_by(
                CustomerContact.is_primary.desc(),
                CustomerContact.is_active.desc(),
                CustomerContact.created_at.asc(),
                CustomerContact.id.asc(),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    def _fallback(customer: Customer) -> dict[str, Any]:
        return {
            "id": None,
            "customer_id": customer.id,
            "name": None,
            "role": None,
            "phone": customer.phone,
            "email": customer.email,
            "is_primary": True,
            "is_active": True,
            "created_at": customer.created_at,
            "updated_at": customer.created_at,
            "is_legacy": True,
        }

    @staticmethod
    async def list_contacts(
        session: AsyncSession, customer_id: int, *, tenant_scope: TenantScope
    ) -> Optional[dict[str, Any]]:
        customer = await CustomerContactService._lock_customer(
            session, customer_id, tenant_scope, lock=False
        )
        if customer is None:
            return None
        contacts = await CustomerContactService._contacts(session, customer_id)
        items = [CustomerContactService._contact_item(c) for c in contacts]
        if not items:
            items = [CustomerContactService._fallback(customer)]
        return {"items": items}

    @staticmethod
    def _append_history(
        session: AsyncSession,
        *,
        customer_id: int,
        contact_id: Optional[int],
        field_name: str,
        old_value: Any,
        new_value: Any,
        author_id: Optional[int],
        author_name: Optional[str],
    ) -> None:
        old = None if old_value is None else str(old_value)
        new = None if new_value is None else str(new_value)
        if old == new:
            return
        session.add(
            CustomerContactHistory(
                customer_id=customer_id,
                contact_id=contact_id,
                field_name=field_name,
                old_value=old,
                new_value=new,
                author_id=author_id,
                author_name=author_name,
                changed_at=datetime.now(timezone.utc),
            )
        )

    @staticmethod
    async def _materialize_fallback(
        session: AsyncSession,
        customer: Customer,
        *,
        author_id: Optional[int],
        author_name: Optional[str],
    ) -> list[CustomerContact]:
        contacts = await CustomerContactService._contacts(session, int(customer.id))
        if contacts:
            return contacts
        fallback = CustomerContact(
            customer_id=int(customer.id),
            name=None,
            phone=customer.phone,
            email=customer.email,
            is_primary=True,
            is_active=True,
            is_legacy=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(fallback)
        await session.flush()
        for field in ("name", "phone", "email", "is_primary", "is_active"):
            CustomerContactService._append_history(
                session,
                customer_id=int(customer.id),
                contact_id=fallback.id,
                field_name=field,
                old_value=None,
                new_value=getattr(fallback, field),
                author_id=author_id,
                author_name=author_name,
            )
        return [fallback]

    @staticmethod
    async def _set_primary(
        session: AsyncSession,
        customer: Customer,
        contact: CustomerContact,
        contacts: list[CustomerContact],
        *,
        author_id: Optional[int],
        author_name: Optional[str],
    ) -> None:
        for other in contacts:
            if other.id != contact.id and other.is_primary:
                old_primary = other.is_primary
                other.is_primary = False
                other.updated_at = datetime.now(timezone.utc)
                CustomerContactService._append_history(
                    session,
                    customer_id=int(customer.id),
                    contact_id=other.id,
                    field_name="is_primary",
                    old_value=old_primary,
                    new_value=False,
                    author_id=author_id,
                    author_name=author_name,
                )
        await session.flush()
        old = contact.is_primary
        contact.is_primary = True
        contact.is_active = True
        if not old:
            CustomerContactService._append_history(
                session,
                customer_id=int(customer.id),
                contact_id=contact.id,
                field_name="is_primary",
                old_value=False,
                new_value=True,
                author_id=author_id,
                author_name=author_name,
            )
        customer.phone = contact.phone or ""
        customer.email = contact.email

    @staticmethod
    async def create_contact(
        session: AsyncSession,
        customer_id: int,
        payload: dict[str, Any],
        *,
        tenant_scope: TenantScope,
        author_id: Optional[int] = None,
        author_name: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        customer = await CustomerContactService._lock_customer(session, customer_id, tenant_scope)
        if customer is None:
            return None
        values = {field: payload[field] for field in CONTACT_FIELDS if field in payload}
        values["name"] = CustomerContactService._clean(values.get("name"))
        if not values["name"]:
            raise ValueError("Имя контактного лица обязательно")
        for field in ("role", "phone", "email"):
            if field in values:
                values[field] = CustomerContactService._clean(values[field])
        make_primary = bool(values.get("is_primary", False))
        is_active = bool(values.get("is_active", True))
        if make_primary and not is_active:
            raise ValueError("Основное контактное лицо должно быть активным")
        contacts = await CustomerContactService._materialize_fallback(
            session, customer, author_id=author_id, author_name=author_name
        )
        now = datetime.now(timezone.utc)
        reusable_fallback = (
            make_primary
            and len(contacts) == 1
            and contacts[0].is_legacy
            and contacts[0].is_primary
        )
        if reusable_fallback:
            contact = contacts[0]
            for field in ("name", "role", "phone", "email"):
                if field not in values:
                    continue
                old_value = getattr(contact, field)
                new_value = values[field]
                if old_value == new_value:
                    continue
                setattr(contact, field, new_value)
                CustomerContactService._append_history(
                    session,
                    customer_id=customer_id,
                    contact_id=contact.id,
                    field_name=field,
                    old_value=old_value,
                    new_value=new_value,
                    author_id=author_id,
                    author_name=author_name,
                )
            contact.is_legacy = False
            contact.updated_at = now
            customer.phone = contact.phone or ""
            customer.email = contact.email
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError("У клиента уже есть основное контактное лицо") from exc
            return CustomerContactService._contact_item(contact)
        if make_primary:
            for existing in contacts:
                if existing.is_primary:
                    existing.is_primary = False
                    existing.updated_at = now
                    CustomerContactService._append_history(
                        session, customer_id=customer_id, contact_id=existing.id,
                        field_name="is_primary", old_value=True, new_value=False,
                        author_id=author_id, author_name=author_name,
                    )
            await session.flush()
        contact = CustomerContact(
            customer_id=customer_id,
            name=values["name"],
            role=values.get("role"),
            phone=values.get("phone"),
            email=values.get("email"),
            is_primary=make_primary,
            is_active=is_active,
            is_legacy=False,
            created_at=now,
            updated_at=now,
        )
        session.add(contact)
        await session.flush()
        for field in CONTACT_FIELDS:
            if field in {"name", "role", "phone", "email", "is_primary", "is_active"}:
                CustomerContactService._append_history(
                    session, customer_id=customer_id, contact_id=contact.id,
                    field_name=field, old_value=None, new_value=getattr(contact, field),
                    author_id=author_id, author_name=author_name,
                )
        if contact.is_primary:
            customer.phone = contact.phone or ""
            customer.email = contact.email
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError("У клиента уже есть основное контактное лицо") from exc
        return CustomerContactService._contact_item(contact)

    @staticmethod
    async def patch_contact(
        session: AsyncSession,
        customer_id: int,
        contact_id: int,
        payload: dict[str, Any],
        *,
        tenant_scope: TenantScope,
        author_id: Optional[int] = None,
        author_name: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        customer = await CustomerContactService._lock_customer(session, customer_id, tenant_scope)
        if customer is None:
            return None
        contacts = await CustomerContactService._contacts(session, customer_id)
        contact = next((item for item in contacts if item.id == contact_id), None)
        if contact is None:
            return None
        values = {field: payload[field] for field in CONTACT_FIELDS if field in payload}
        if values.get("name") is None:
            values.pop("name", None)
        for field in ("is_primary", "is_active"):
            if values.get(field) is None:
                values.pop(field, None)
        if "name" in values:
            values["name"] = CustomerContactService._clean(values["name"])
            if not values["name"]:
                raise ValueError("Имя контактного лица обязательно")
        for field in ("role", "phone", "email"):
            if field in values:
                values[field] = CustomerContactService._clean(values[field])
        if values.get("is_primary") and values.get("is_active") is False:
            raise ValueError("Основное контактное лицо должно быть активным")
        if contact.is_primary and contact.is_active and (
            values.get("is_primary") is False or values.get("is_active") is False
        ):
            has_other_active = any(
                item.id != contact.id and item.is_active for item in contacts
            )
            if not has_other_active:
                raise ValueError("Сначала выберите другое основное контактное лицо")
        old_primary = bool(contact.is_primary)
        changed_primary = bool(values.get("is_primary", old_primary)) and bool(
            values.get("is_active", contact.is_active)
        )
        now = datetime.now(timezone.utc)
        for field, value in values.items():
            # Let _set_primary flush all demotions before it marks this row
            # primary, otherwise this flush would promote both rows at once.
            if field == "is_primary" and value is True:
                continue
            old = getattr(contact, field)
            if old == value:
                continue
            setattr(contact, field, value)
            contact.updated_at = now
            CustomerContactService._append_history(
                session, customer_id=customer_id, contact_id=contact.id,
                field_name=field, old_value=old, new_value=value,
                author_id=author_id, author_name=author_name,
            )
        if values and contact.is_legacy:
            contact.is_legacy = False
        if changed_primary:
            await CustomerContactService._set_primary(
                session, customer, contact, contacts,
                author_id=author_id, author_name=author_name,
            )
        elif old_primary and (not contact.is_active or not contact.is_primary):
            replacement = next((c for c in contacts if c.id != contact.id and c.is_active), None)
            if replacement:
                await CustomerContactService._set_primary(
                    session, customer, replacement, contacts,
                    author_id=author_id, author_name=author_name,
                )
        elif old_primary:
            customer.phone = contact.phone or ""
            customer.email = contact.email
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise ValueError("У клиента уже есть основное контактное лицо") from exc
        return CustomerContactService._contact_item(contact)

    @staticmethod
    async def sync_primary_fields(
        session: AsyncSession,
        customer: Customer,
        *,
        phone: Optional[str],
        email: Optional[str],
        author_id: Optional[int] = None,
        author_name: Optional[str] = None,
    ) -> None:
        """Keep a real primary contact aligned with trusted requisites updates."""
        result = await session.execute(
            select(CustomerContact).where(
                CustomerContact.customer_id == customer.id,
                CustomerContact.is_primary.is_(True),
                CustomerContact.is_active.is_(True),
            ).with_for_update()
        )
        contact = result.scalars().first()
        if contact is None:
            return
        for field, value in (("phone", phone), ("email", email)):
            cleaned = CustomerContactService._clean(value)
            old = getattr(contact, field)
            if old == cleaned:
                continue
            setattr(contact, field, cleaned)
            CustomerContactService._append_history(
                session,
                customer_id=int(customer.id),
                contact_id=contact.id,
                field_name=field,
                old_value=old,
                new_value=cleaned,
                author_id=author_id,
                author_name=author_name,
            )
        contact.updated_at = datetime.now(timezone.utc)

    @staticmethod
    async def history(
        session: AsyncSession, customer_id: int, *, tenant_scope: TenantScope,
        page: int = 1, limit: int = 50,
    ) -> Optional[dict[str, Any]]:
        customer = await CustomerContactService._lock_customer(
            session, customer_id, tenant_scope, lock=False
        )
        if customer is None:
            return None
        total_result = await session.execute(
            select(func.count(CustomerContactHistory.id)).where(
                CustomerContactHistory.customer_id == customer_id
            )
        )
        total = int(total_result.scalar() or 0)
        result = await session.execute(
            select(CustomerContactHistory)
            .where(CustomerContactHistory.customer_id == customer_id)
            .order_by(CustomerContactHistory.changed_at.desc(), CustomerContactHistory.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return {
            "items": [CustomerContactService._history_item(row) for row in result.scalars().all()],
            "meta": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit if limit else 1,
            },
        }

    @staticmethod
    async def summaries(
        session: AsyncSession, customers: list[Customer]
    ) -> dict[int, tuple[dict[str, Any], int]]:
        ids = [int(customer.id) for customer in customers if customer.id is not None]
        contacts_by_customer: dict[int, list[CustomerContact]] = {}
        if ids:
            result = await session.execute(
                select(CustomerContact)
                .where(CustomerContact.customer_id.in_(ids))
                .order_by(
                    CustomerContact.is_primary.desc(),
                    CustomerContact.is_active.desc(),
                    CustomerContact.created_at.asc(),
                    CustomerContact.id.asc(),
                )
            )
            for contact in result.scalars().all():
                contacts_by_customer.setdefault(contact.customer_id, []).append(contact)
        summaries: dict[int, tuple[dict[str, Any], int]] = {}
        for customer in customers:
            cid = int(customer.id or 0)
            contacts = contacts_by_customer.get(cid, [])
            primary = next(
                (contact for contact in contacts if contact.is_primary and contact.is_active),
                None,
            )
            if primary:
                item = CustomerContactService._contact_item(primary)
            elif contacts:
                item = None
            else:
                item = CustomerContactService._fallback(customer)
            summaries[cid] = (item, len(contacts))
        return summaries
