import pytest

from services.order_scenarios import SCENARIOS, WORK_SCENARIO, infer_scenario_from_task, resolve_scenario


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


@pytest.mark.parametrize(
    ("task", "expected"),
    [
        ("Техническое обслуживание кондиционеров", "maintenance"),
        ("Профилактическое обслуживание сплит-систем", "maintenance"),
        ("Ремонт кондиционеров в офисе", "repair"),
        ("Поставка кондиционеров и монтаж кондиционеров", "turnkey"),
        ("Поставка и монтаж кондиционеров", "turnkey"),
        ("Монтаж кондиционеров заказчика", "install_only"),
        ("Монтаж нового кондиционера без переноса существующего кондиционера", "install_only"),
        ("Техническое обслуживание и ремонт кондиционеров", None),
        ("Поставка кондиционеров с гарантийным обслуживанием", None),
        ("Кондиционеры для здания", None),
    ],
)
def test_scenario_suggestion_needs_clear_task(task, expected):
    suggestion = infer_scenario_from_task(task)
    assert (suggestion.service_type if suggestion else None) == expected


@pytest.mark.parametrize("task", [
    "Текущий ремонт помещений по адресу г. Лепель, пл. Свободы, 1 (перенос кондиционера)",
    "Перенос исправной сплит-системы: демонтаж по адресу 11-2 и монтаж по адресу 1.",
    "Демонтировать и перенести существующий кондиционер с последующей установкой.",
])
def test_relocation_uses_general_works_instead_of_dismantling(task):
    assert infer_scenario_from_task(task) == WORK_SCENARIO
