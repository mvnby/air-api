from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.config import settings
from models import AnalyticsConnection, DocumentDriveConnection
from services.analytics_connection_contracts import (
    YANDEX_METRIKA,
    AnalyticsConnectionError,
    AnalyticsCredentialCipher,
)
from services.document_drive_contracts import (
    DocumentDriveConnectionError,
    DocumentDriveCredentialCipher,
)
from services.integration_credential_rotation_token import (
    IntegrationCredentialRotationBlockedError,
    IntegrationCredentialRotationToken,
)


_ADVISORY_LOCK_KEY = "mvn:integration-credential-rewrap:v1"
_MAX_ROWS = 10_000


@dataclass(frozen=True, slots=True)
class _RotationRecord:
    domain: Literal["analytics", "document_drive"]
    row: AnalyticsConnection | DocumentDriveConnection
    source: Literal["active", "retained", "legacy", "unreadable"]
    credentials: dict[str, Any] | None
    needs_rewrap: bool

    def sanitized(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "domain": self.domain,
            "id": int(self.row.id or 0),
            "tenant_id": int(self.row.tenant_id),
            "provider": str(self.row.provider),
            "status": str(self.row.status),
            "source": self.source,
            "needs_rewrap": self.needs_rewrap,
            "ciphertext_sha256": hashlib.sha256(
                self.row.encrypted_credentials.encode("utf-8")
            ).hexdigest(),
            "fingerprint_sha256": hashlib.sha256(
                self.row.credentials_fingerprint.encode("utf-8")
            ).hexdigest(),
        }
        if isinstance(self.row, AnalyticsConnection):
            value["storefront_id"] = int(self.row.storefront_id)
        return value


class IntegrationCredentialRotationService:
    """Plan and atomically rewrap persisted integration credentials."""

    @classmethod
    async def plan(cls, session: AsyncSession) -> dict[str, Any]:
        records = await cls._read_records(session, for_update=False)
        plan = cls._build_plan(records)
        if plan["ready"]:
            plan["plan_token"] = IntegrationCredentialRotationToken.issue(
                plan_digest=plan["plan_digest"]
            )
        return plan

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        plan_token: str,
    ) -> dict[str, Any]:
        keyring = settings.integration_credential_keyring
        if not keyring.enabled or keyring.write_mode != "active":
            raise IntegrationCredentialRotationBlockedError(
                "Execute requires active integration credential writes"
            )
        verified = IntegrationCredentialRotationToken.verify(plan_token)
        await cls._lock_primary_transaction(session)
        records = await cls._read_records(session, for_update=True)
        reviewed = cls._build_plan(records)
        if not reviewed["ready"]:
            raise IntegrationCredentialRotationBlockedError(
                "Current credential state has blockers; run a fresh plan"
            )
        if not hmac.compare_digest(
            verified.plan_digest,
            reviewed["plan_digest"],
        ):
            raise IntegrationCredentialRotationBlockedError(
                "Credential state changed after review; run a fresh plan"
            )

        changed = 0
        for record in records:
            if not record.needs_rewrap:
                continue
            if record.credentials is None:
                raise IntegrationCredentialRotationBlockedError(
                    "Current credential state has blockers; run a fresh plan"
                )
            cls._rewrap_record(record)
            session.add(record.row)
            changed += 1
        await session.flush()
        return {
            "status": "completed",
            "reviewed_plan_digest": reviewed["plan_digest"],
            "rewrapped": changed,
            "unchanged": len(records) - changed,
            "total": len(records),
            "active_key_id": keyring.active_key_id,
        }

    @classmethod
    async def _read_records(
        cls,
        session: AsyncSession,
        *,
        for_update: bool,
    ) -> list[_RotationRecord]:
        analytics_query = select(AnalyticsConnection).order_by(AnalyticsConnection.id)
        drive_query = select(DocumentDriveConnection).order_by(DocumentDriveConnection.id)
        if for_update:
            analytics_query = analytics_query.with_for_update()
            drive_query = drive_query.with_for_update()
        analytics_rows = (await session.execute(analytics_query)).scalars().all()
        drive_rows = (await session.execute(drive_query)).scalars().all()
        if len(analytics_rows) + len(drive_rows) > _MAX_ROWS:
            raise IntegrationCredentialRotationBlockedError(
                "Credential row limit exceeded"
            )
        records = [cls._analytics_record(row) for row in analytics_rows]
        records.extend(cls._drive_record(row) for row in drive_rows)
        return records

    @staticmethod
    def _analytics_record(row: AnalyticsConnection) -> _RotationRecord:
        try:
            credentials, decrypted = AnalyticsCredentialCipher.decrypt_with_source(
                row.encrypted_credentials,
                tenant_id=row.tenant_id,
                storefront_id=row.storefront_id,
                provider=row.provider,
            )
        except AnalyticsConnectionError:
            return _RotationRecord("analytics", row, "unreadable", None, False)
        fingerprint_matches = (
            decrypted.source == "active"
            and hmac.compare_digest(
                row.credentials_fingerprint,
                AnalyticsCredentialCipher.fingerprint(
                    IntegrationCredentialRotationService._analytics_fingerprint_source(
                        row.provider,
                        credentials,
                    )
                ),
            )
        )
        return _RotationRecord(
            "analytics",
            row,
            decrypted.source,
            credentials,
            not fingerprint_matches,
        )

    @staticmethod
    def _drive_record(row: DocumentDriveConnection) -> _RotationRecord:
        try:
            credentials, decrypted = DocumentDriveCredentialCipher.decrypt_with_source(
                row.encrypted_credentials,
                tenant_id=row.tenant_id,
                provider=row.provider,
            )
        except DocumentDriveConnectionError:
            return _RotationRecord("document_drive", row, "unreadable", None, False)
        fingerprint_matches = (
            decrypted.source == "active"
            and hmac.compare_digest(
                row.credentials_fingerprint,
                DocumentDriveCredentialCipher.fingerprint(credentials),
            )
        )
        return _RotationRecord(
            "document_drive",
            row,
            decrypted.source,
            credentials,
            not fingerprint_matches,
        )

    @classmethod
    def _build_plan(cls, records: list[_RotationRecord]) -> dict[str, Any]:
        keyring = settings.integration_credential_keyring
        rows = [record.sanitized() for record in records]
        counts = {
            source: sum(record.source == source for record in records)
            for source in ("active", "retained", "legacy", "unreadable")
        }
        counts["fingerprint_drift"] = sum(
            record.source == "active" and record.needs_rewrap
            for record in records
        )
        plan_body = {
            "version": 1,
            "active_key_id": keyring.active_key_id if keyring.enabled else None,
            "write_mode": keyring.write_mode,
            "counts": counts,
            "rows": rows,
        }
        encoded = json.dumps(
            plan_body,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        ready = bool(
            keyring.enabled
            and keyring.write_mode == "active"
            and counts["unreadable"] == 0
        )
        return {
            **plan_body,
            "ready": ready,
            "complete": (
                ready
                and counts["retained"] == 0
                and counts["legacy"] == 0
                and counts["fingerprint_drift"] == 0
            ),
            "plan_digest": hashlib.sha256(encoded).hexdigest(),
            "blockers": cls._blockers(keyring.enabled, keyring.write_mode, counts),
        }

    @staticmethod
    def _blockers(
        keyring_enabled: bool,
        write_mode: str,
        counts: dict[str, int],
    ) -> list[str]:
        blockers: list[str] = []
        if not keyring_enabled:
            blockers.append("integration_keyring_missing")
        elif write_mode != "active":
            blockers.append("active_writes_not_enabled")
        if counts["unreadable"]:
            blockers.append("credentials_unreadable")
        return blockers

    @staticmethod
    def _rewrap_record(record: _RotationRecord) -> None:
        credentials = record.credentials
        if credentials is None:
            raise IntegrationCredentialRotationBlockedError(
                "Credential row cannot be rewrapped"
            )
        if isinstance(record.row, AnalyticsConnection):
            record.row.encrypted_credentials = AnalyticsCredentialCipher.encrypt(
                credentials,
                tenant_id=record.row.tenant_id,
                storefront_id=record.row.storefront_id,
                provider=record.row.provider,
            )
            record.row.credentials_fingerprint = AnalyticsCredentialCipher.fingerprint(
                IntegrationCredentialRotationService._analytics_fingerprint_source(
                    record.row.provider,
                    credentials,
                )
            )
            return
        record.row.encrypted_credentials = DocumentDriveCredentialCipher.encrypt(
            credentials,
            tenant_id=record.row.tenant_id,
            provider=record.row.provider,
        )
        record.row.credentials_fingerprint = DocumentDriveCredentialCipher.fingerprint(
            credentials
        )

    @staticmethod
    def _analytics_fingerprint_source(
        provider: str,
        credentials: dict[str, Any],
    ) -> str:
        if provider == YANDEX_METRIKA:
            return str(credentials.get("oauth_token") or "")
        return json.dumps(
            credentials,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

    @staticmethod
    async def _lock_primary_transaction(session: AsyncSession) -> None:
        if session.get_bind().dialect.name != "postgresql":
            raise IntegrationCredentialRotationBlockedError(
                "Execute requires PostgreSQL primary"
            )
        in_recovery = bool(
            (await session.execute(text("SELECT pg_is_in_recovery()"))).scalar_one()
        )
        read_only = str(
            (await session.execute(text("SHOW transaction_read_only"))).scalar_one()
        ).lower()
        if in_recovery or read_only != "off":
            raise IntegrationCredentialRotationBlockedError(
                "Execute requires a writable PostgreSQL primary"
            )
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
            {"lock_key": _ADVISORY_LOCK_KEY},
        )


__all__ = ["IntegrationCredentialRotationService"]
