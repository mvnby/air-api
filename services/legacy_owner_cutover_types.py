"""Internal state carriers for the legacy-owner cutover service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from models import LegacyOwnerAuthState, StaffUser, Storefront, Tenant, TenantMembership


@dataclass(frozen=True)
class LegacyOwnerRuntimeIdentity:
    normalized_name: str | None
    credential: str
    policy_compliant: bool
    identity_canonical: bool
    binding: str


@dataclass
class LegacyOwnerCutoverState:
    auth_state: LegacyOwnerAuthState | None
    tenants: list[Tenant]
    storefronts: list[Storefront]
    candidates: list[StaffUser]
    memberships: list[TenantMembership]
    credential_matches: bool

    @property
    def tenant(self) -> Tenant | None:
        return self.tenants[0] if len(self.tenants) == 1 else None

    @property
    def storefront(self) -> Storefront | None:
        return self.storefronts[0] if len(self.storefronts) == 1 else None

    @property
    def user(self) -> StaffUser | None:
        return self.candidates[0] if len(self.candidates) == 1 else None

    @property
    def membership(self) -> TenantMembership | None:
        return self.memberships[0] if len(self.memberships) == 1 else None


LegacyOwnerPlanAction = Literal["cutover", "rollback"]


__all__ = [
    "LegacyOwnerCutoverState",
    "LegacyOwnerPlanAction",
    "LegacyOwnerRuntimeIdentity",
]
