from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from models.tenancy import TenantScope


INTERNAL_STOCK_RULE_FIELD = "public_stock_states"


class ProductCollectionRulePolicy:
    """Protect internal sourcing signals at the collection rule boundary."""

    @staticmethod
    def has_internal_stock_rule(rule_config: dict[str, Any]) -> bool:
        return bool(rule_config.get(INTERNAL_STOCK_RULE_FIELD))

    @classmethod
    def validate_write(
        cls,
        *,
        rule_config: dict[str, Any],
        tenant_scope: TenantScope,
    ) -> None:
        if tenant_scope.is_system or not cls.has_internal_stock_rule(rule_config):
            return
        raise HTTPException(
            status_code=403,
            detail="Фильтрация подборок по внутреннему источнику наличия недоступна для этой витрины.",
        )

    @classmethod
    def allows_automatic_matching(
        cls,
        *,
        rule_config: dict[str, Any],
        disclose_internal_stock: bool,
    ) -> bool:
        return disclose_internal_stock or not cls.has_internal_stock_rule(rule_config)

    @staticmethod
    def project_for_manager(
        rule_config: dict[str, Any],
        *,
        tenant_scope: TenantScope,
    ) -> dict[str, Any]:
        projected = dict(rule_config)
        if not tenant_scope.is_system:
            projected[INTERNAL_STOCK_RULE_FIELD] = []
        return projected


__all__ = ["ProductCollectionRulePolicy"]
