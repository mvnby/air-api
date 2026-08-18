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
    ]


def test_system_owner_gets_platform_staff_and_infrastructure_capabilities():
    assert ManagerCapabilityService.for_auth(
        _auth(role="owner", is_system=True)
    ) == list(ManagerCapabilityService.ORDERED_CAPABILITIES)


def test_non_system_owner_does_not_gain_platform_capabilities():
    capabilities = ManagerCapabilityService.for_auth(
        _auth(role="owner", is_system=False)
    )
    assert "staff.manage" in capabilities
    assert "platform.manage" not in capabilities
    assert "infrastructure.manage" not in capabilities
