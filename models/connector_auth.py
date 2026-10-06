"""Durable, secret-free OAuth state for the personal Kitlane connector."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, JSON, String
from sqlmodel import Field, SQLModel


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorGrant(SQLModel, table=True):
    __tablename__ = "connector_grant"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_connector_grant_storefront_tenant",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    staff_user_id: int = Field(foreign_key="staff_users.id", index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    storefront_id: int = Field(foreign_key="storefront.id")
    membership_id: int = Field(foreign_key="tenant_membership.id")
    auth_version: int
    role: str
    client_id: str
    resource: str
    scopes: list[str] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    revoked_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class ConnectorConsent(SQLModel, table=True):
    __tablename__ = "connector_consent"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_connector_consent_storefront_tenant",
        ),
    )
    id: str = Field(primary_key=True)
    staff_user_id: int = Field(foreign_key="staff_users.id")
    tenant_id: int = Field(foreign_key="tenant.id")
    storefront_id: int = Field(foreign_key="storefront.id")
    membership_id: int = Field(foreign_key="tenant_membership.id")
    auth_version: int
    role: str
    session_hash: str
    csrf_hash: str
    client_id: str
    redirect_uri: str
    resource: str
    scopes: list[str] = Field(sa_column=Column(JSON, nullable=False))
    state: str
    code_challenge: str
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    consumed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class ConnectorAuthorizationCode(SQLModel, table=True):
    __tablename__ = "connector_authorization_code"
    id: Optional[int] = Field(default=None, primary_key=True)
    code_hash: str = Field(
        sa_column=Column(String(64), unique=True, nullable=False, index=True)
    )
    grant_id: int = Field(foreign_key="connector_grant.id", index=True)
    redirect_uri: str
    code_challenge: str
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    consumed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class ConnectorToken(SQLModel, table=True):
    __tablename__ = "connector_token"
    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(
        sa_column=Column(String(64), unique=True, nullable=False, index=True)
    )
    grant_id: int = Field(foreign_key="connector_grant.id", index=True)
    kind: str
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    consumed_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True))
    )


class ConnectorAuthEvent(SQLModel, table=True):
    __tablename__ = "connector_auth_event"
    id: Optional[int] = Field(default=None, primary_key=True)
    grant_id: int = Field(foreign_key="connector_grant.id", index=True)
    staff_user_id: int = Field(foreign_key="staff_users.id", index=True)
    operation: str
    channel: str = Field(default="chatgpt")
    created_at: datetime = Field(
        default_factory=now_utc,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
