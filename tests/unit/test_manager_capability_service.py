from dataclasses import replace

import pytest

from core.config import settings
from core.security import AuthenticatedUser
from services.manager_capability_service import ManagerCapabilityService


def _auth(*, role: str, is_system: bool) -> AuthenticatedUser:
    return AuthenticatedUser(
        username="manager",
        auth_source="test",
        staff_user_id=1,
        role=role,
        tenant_id=1,
        storefront_id=1,
        tenant_membership_id=1,
        is_system_tenant=is_system,
    )


def test_non_system_manager_gets_only_tenant_work_capabilities():
    assert ManagerCapabilityService.for_auth(
        _auth(role="manager", is_system=False)
    ) == [
        "crm.manage",
        "catalog.master.read",
        "storefront.offers.read",
        "storefront.collections.manage",
        "services.manage",
    ]


def test_system_owner_gets_standard_capabilities_without_private_pilot():
    assert ManagerCapabilityService.for_auth(
        _auth(role="owner", is_system=True)
    ) == [
        capability for capability in ManagerCapabilityService.ORDERED_CAPABILITIES
        if capability != ManagerCapabilityService.CALL_RECORDINGS_MANAGE
    ]


def test_non_system_owner_does_not_gain_platform_capabilities():
    capabilities = ManagerCapabilityService.for_auth(
        _auth(role="owner", is_system=False)
    )
    assert "staff.manage" in capabilities
    assert "analytics.manage" in capabilities
    assert "documents.manage" in capabilities
    assert "settings.manage" in capabilities
    assert "services.manage" in capabilities
    assert "platform.manage" not in capabilities
    assert "infrastructure.manage" not in capabilities


@pytest.mark.parametrize("role", ["owner", "admin", "manager"])
@pytest.mark.parametrize("is_system", [True, False])
def test_private_calls_require_explicit_staff_access_even_for_owners(monkeypatch, role, is_system):
    auth = _auth(role=role, is_system=is_system)
    monkeypatch.setattr(settings, "CALL_RECORDINGS_PILOT_STAFF_IDS", [])
    assert "call_recordings.manage" not in ManagerCapabilityService.for_auth(auth)
    monkeypatch.setattr(settings, "CALL_RECORDINGS_PILOT_STAFF_IDS", [4])
    assert "call_recordings.manage" not in ManagerCapabilityService.for_auth(auth)
    assert "call_recordings.manage" in ManagerCapabilityService.for_auth(replace(auth, staff_user_id=4))


def test_private_calls_do_not_restore_a_revoked_manager_role(monkeypatch):
    monkeypatch.setattr(settings, "CALL_RECORDINGS_PILOT_STAFF_IDS", [1])
    assert "call_recordings.manage" not in ManagerCapabilityService.for_auth(_auth(role="installer", is_system=True))
