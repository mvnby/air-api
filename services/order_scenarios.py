"""Shared interactive order scenarios and their persisted workflow mapping."""

from typing import NamedTuple, Optional


class OrderScenario(NamedTuple):
    label: str
    workflow_type: str
    service_type: Optional[str]
    hint: str = ""


SCENARIOS = (
    OrderScenario("Продажа + монтаж", "sales_installation", "turnkey"),
    OrderScenario("Монтаж", "service_work", "install_only"),
    OrderScenario("Обслуживание", "maintenance", "maintenance"),
    OrderScenario("Ремонт", "repair", "repair"),
    OrderScenario("Работы", "service_work", None, "Вид работ можно уточнить позже"),
    OrderScenario("Закладка трассы", "service_work", "pre_install"),
    OrderScenario("Демонтаж", "service_work", "dismantling"),
)

SERVICE_TYPE_LABELS = {
    scenario.service_type: scenario.label
    for scenario in SCENARIOS
    if scenario.service_type is not None
}
SERVICE_TYPE_WORKFLOWS = {
    scenario.service_type: scenario.workflow_type
    for scenario in SCENARIOS
    if scenario.service_type is not None
}
WORKFLOW_TYPES = frozenset(scenario.workflow_type for scenario in SCENARIOS)
WORKFLOW_LABELS = {
    "sales_installation": "Продажа + монтаж",
    "service_work": "Работы",
    "maintenance": "Обслуживание",
    "repair": "Ремонт",
}


def workflow_for_service_type(service_type: str) -> str:
    try:
        return SERVICE_TYPE_WORKFLOWS[service_type]
    except KeyError as exc:
        raise ValueError(f"Unknown service_type: {service_type}") from exc


def resolve_scenario(
    *, workflow_type: Optional[str], service_type: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Validate an explicitly selected scenario, preserving an absent legacy choice."""
    if workflow_type is not None and workflow_type not in WORKFLOW_TYPES:
        raise ValueError(f"Unknown workflow_type: {workflow_type}")
    if service_type is not None:
        mapped = workflow_for_service_type(service_type)
        if workflow_type is not None and workflow_type != mapped:
            raise ValueError("service_type conflicts with workflow_type")
        return mapped, service_type
    if workflow_type is not None and workflow_type != "service_work":
        # Each non-generic workflow has one canonical service type.
        canonical = next(
            scenario.service_type
            for scenario in SCENARIOS
            if scenario.workflow_type == workflow_type and scenario.service_type is not None
        )
        return workflow_type, canonical
    return workflow_type, None
