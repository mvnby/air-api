import pytest

from services.order_scenarios import SCENARIOS, resolve_scenario


@pytest.mark.parametrize(
    ("service_type", "workflow_type"),
    [
        ("turnkey", "sales_installation"),
        ("install_only", "service_work"),
        ("pre_install", "service_work"),
        ("dismantling", "service_work"),
        ("maintenance", "maintenance"),
        ("repair", "repair"),
    ],
)
def test_service_type_has_one_workflow(service_type, workflow_type):
    assert resolve_scenario(workflow_type=None, service_type=service_type) == (
        workflow_type, service_type,
    )


def test_generic_works_is_supported_without_service_type():
    assert resolve_scenario(workflow_type="service_work", service_type=None) == (
        "service_work", None,
    )
    assert any(
        item.workflow_type == "service_work" and item.service_type is None
        for item in SCENARIOS
    )


@pytest.mark.parametrize(
    ("workflow_type", "service_type"),
    [("maintenance", "install_only"), ("invalid", None), (None, "other")],
)
def test_invalid_scenario_is_rejected(workflow_type, service_type):
    with pytest.raises(ValueError):
        resolve_scenario(workflow_type=workflow_type, service_type=service_type)
