from __future__ import annotations

import pytest

from modules.documents.application.artifact_helpers import _condition_values


def test_condition_values_require_complete_boolean_snapshot() -> None:
    catalog = frozenset(
        {
            "seller.is_individual_entrepreneur",
            "customer.is_organization",
        }
    )

    with pytest.raises(ValueError, match="отсутствуют условные флаги"):
        _condition_values(
            catalog,
            {"seller.is_individual_entrepreneur": True},
        )
    with pytest.raises(TypeError, match="должен быть boolean"):
        _condition_values(
            catalog,
            {
                "seller.is_individual_entrepreneur": "false",
                "customer.is_organization": True,
            },
        )


def test_condition_values_keep_old_conditionless_templates_compatible() -> None:
    assert _condition_values(frozenset(), None) == {}
