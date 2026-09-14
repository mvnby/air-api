"""Detached copying of the canonical MVN service and pricing dictionaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.request_context import current_request_id
from models import (
    InstallationRate,
    Service,
    ServiceTariff,
    ServiceTariffRule,
    Storefront,
    TenantAuditEvent,
)
from models.tenancy import TenantScope
from schemas_service_catalog import (
    ManagerServiceCatalogCloneResponse,
    ManagerServiceCatalogTemplatePreviewResponse,
    ServiceCatalogCounts,
)
from services.command_transaction import command_transaction
from services.service_catalog_scope import canonical_service_catalog_clause


@dataclass(frozen=True)
class _CanonicalTemplate:
    services: list[Service]
    tariffs: list[ServiceTariff]
    rates: list[InstallationRate]

    @property
    def rules(self) -> list[ServiceTariffRule]:
        return [rule for tariff in self.tariffs for rule in list(tariff.rules or [])]

    @property
    def counts(self) -> ServiceCatalogCounts:
        return ServiceCatalogCounts(
            services=len(self.services),
            tariffs=len(self.tariffs),
            tariff_rules=len(self.rules),
            installation_rates=len(self.rates),
        )


class ServiceCatalogTemplateService:
    @staticmethod
    async def _load_source(
        session: AsyncSession,
        *,
        lock: bool = False,
    ) -> _CanonicalTemplate:
        services_stmt = (
            select(Service)
            .where(
                canonical_service_catalog_clause(Service),
                Service.is_active.is_(True),
            )
            .order_by(Service.id)
        )
        tariffs_stmt = (
            select(ServiceTariff)
            .where(canonical_service_catalog_clause(ServiceTariff))
            .options(selectinload(ServiceTariff.rules))
            .order_by(ServiceTariff.id)
        )
        rates_stmt = (
            select(InstallationRate)
            .where(canonical_service_catalog_clause(InstallationRate))
            .order_by(InstallationRate.id)
        )
        if lock:
            services_stmt = services_stmt.with_for_update()
            tariffs_stmt = tariffs_stmt.with_for_update()
            rates_stmt = rates_stmt.with_for_update()

        services = list((await session.execute(services_stmt)).scalars().all())
        tariffs = list((await session.execute(tariffs_stmt)).scalars().unique().all())
        rates = list((await session.execute(rates_stmt)).scalars().all())
        return _CanonicalTemplate(services=services, tariffs=tariffs, rates=rates)

    @staticmethod
    def _fingerprint(template: _CanonicalTemplate) -> str:
        payload = {
            "services": [
                {
                    "id": row.id,
                    "title": row.title,
                    "slug": row.slug,
                    "category": row.category,
                    "is_active": row.is_active,
                    "image": row.image,
                    "description": row.description,
                    "base_price": row.base_price,
                }
                for row in template.services
            ],
            "tariffs": [
                {
                    "id": row.id,
                    "service_kind": row.service_kind,
                    "selector_label": row.selector_label,
                    "estimate_template": row.estimate_template,
                    "short_name": row.short_name,
                    "full_description": row.full_description,
                    "category": row.category,
                    "power_range": row.power_range,
                    "base_price": row.base_price,
                    "included_route_meters": float(row.included_route_meters or 0),
                    "is_active": row.is_active,
                    "sort_order": row.sort_order,
                    "comment": row.comment,
                    "rules": [
                        {
                            "id": rule.id,
                            "rule_type": rule.rule_type,
                            "name": rule.name,
                            "line_template": rule.line_template,
                            "unit": rule.unit,
                            "unit_price": float(rule.unit_price or 0),
                            "is_optional": rule.is_optional,
                            "is_favorite": rule.is_favorite,
                            "is_active": rule.is_active,
                            "sort_order": rule.sort_order,
                            "service_id": rule.service_id,
                        }
                        for rule in list(row.rules or [])
                    ],
                }
                for row in template.tariffs
            ],
            "rates": [
                {
                    "id": row.id,
                    "category": row.category,
                    "power_range": row.power_range,
                    "base_price": row.base_price,
                    "extra_pipe_price": row.extra_pipe_price,
                    "included_pipe_meters": row.included_pipe_meters,
                    "is_fixed": row.is_fixed,
                    "comment": row.comment,
                }
                for row in template.rates
            ],
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    async def _target_counts(
        session: AsyncSession,
        tenant_id: int,
    ) -> ServiceCatalogCounts:
        async def count(entity, *clauses) -> int:
            result = await session.execute(
                select(func.count()).select_from(entity).where(*clauses)
            )
            return int(result.scalar_one() or 0)

        return ServiceCatalogCounts(
            services=await count(Service, Service.tenant_id == tenant_id),
            tariffs=await count(ServiceTariff, ServiceTariff.tenant_id == tenant_id),
            tariff_rules=await count(
                ServiceTariffRule,
                ServiceTariffRule.tariff_id == ServiceTariff.id,
                ServiceTariff.tenant_id == tenant_id,
            ),
            installation_rates=await count(
                InstallationRate,
                InstallationRate.tenant_id == tenant_id,
            ),
        )

    @staticmethod
    async def preview(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> ManagerServiceCatalogTemplatePreviewResponse:
        source = await ServiceCatalogTemplateService._load_source(session)
        fingerprint = ServiceCatalogTemplateService._fingerprint(source)
        if tenant_scope.is_system:
            return ManagerServiceCatalogTemplatePreviewResponse(
                source_counts=source.counts,
                source_fingerprint=fingerprint,
                target_counts=source.counts,
                can_clone=False,
            )
        target_counts = await ServiceCatalogTemplateService._target_counts(
            session, tenant_scope.tenant_id
        )
        return ManagerServiceCatalogTemplatePreviewResponse(
            source_counts=source.counts,
            source_fingerprint=fingerprint,
            target_counts=target_counts,
            can_clone=sum(target_counts.model_dump().values()) == 0,
        )

    @staticmethod
    async def _template_is_complete(
        session: AsyncSession,
        *,
        source: _CanonicalTemplate,
        tenant_id: int,
    ) -> bool:
        service_sources = set(
            (
                await session.execute(
                    select(Service.source_service_id).where(
                        Service.tenant_id == tenant_id,
                        Service.source_service_id.is_not(None),
                    )
                )
            ).scalars()
        )
        tariff_sources = set(
            (
                await session.execute(
                    select(ServiceTariff.source_tariff_id).where(
                        ServiceTariff.tenant_id == tenant_id,
                        ServiceTariff.source_tariff_id.is_not(None),
                    )
                )
            ).scalars()
        )
        rate_sources = set(
            (
                await session.execute(
                    select(InstallationRate.source_installation_rate_id).where(
                        InstallationRate.tenant_id == tenant_id,
                        InstallationRate.source_installation_rate_id.is_not(None),
                    )
                )
            ).scalars()
        )
        rule_sources = set(
            (
                await session.execute(
                    select(ServiceTariffRule.source_rule_id)
                    .join(ServiceTariff)
                    .where(
                        ServiceTariff.tenant_id == tenant_id,
                        ServiceTariffRule.source_rule_id.is_not(None),
                    )
                )
            ).scalars()
        )
        return (
            service_sources == {row.id for row in source.services}
            and tariff_sources == {row.id for row in source.tariffs}
            and rate_sources == {row.id for row in source.rates}
            and rule_sources == {row.id for row in source.rules}
        )

    @staticmethod
    async def clone(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
        expected_fingerprint: str,
        actor_username: str | None = None,
        actor_staff_user_id: int | None = None,
    ) -> ManagerServiceCatalogCloneResponse:
        if tenant_scope.is_system:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Canonical tenant already owns the service template",
            )

        async with command_transaction(session):
            storefront = (
                await session.execute(
                    select(Storefront)
                    .where(
                        Storefront.id == tenant_scope.storefront_id,
                        Storefront.tenant_id == tenant_scope.tenant_id,
                    )
                    .with_for_update()
                )
            ).scalars().first()
            if storefront is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Storefront not found",
                )
            source = await ServiceCatalogTemplateService._load_source(
                session, lock=True
            )
            fingerprint = ServiceCatalogTemplateService._fingerprint(source)
            if fingerprint != expected_fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Service template changed; refresh the preview",
                )

            target_counts = await ServiceCatalogTemplateService._target_counts(
                session, tenant_scope.tenant_id
            )
            if sum(target_counts.model_dump().values()) > 0:
                if await ServiceCatalogTemplateService._template_is_complete(
                    session,
                    source=source,
                    tenant_id=tenant_scope.tenant_id,
                ):
                    return ManagerServiceCatalogCloneResponse(
                        status="already_cloned",
                        cloned_counts=source.counts,
                        source_fingerprint=fingerprint,
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        "Tenant service catalog already contains local or partial "
                        "data; existing rows were not overwritten"
                    ),
                )

            service_map: dict[int, int] = {}
            for source_service in source.services:
                cloned = Service(
                    tenant_id=tenant_scope.tenant_id,
                    source_service_id=int(source_service.id),
                    title=source_service.title,
                    slug=source_service.slug,
                    category=source_service.category,
                    is_active=source_service.is_active,
                    image=source_service.image,
                    description=source_service.description,
                    base_price=source_service.base_price,
                )
                session.add(cloned)
                await session.flush()
                service_map[int(source_service.id)] = int(cloned.id)

            for source_tariff in source.tariffs:
                cloned_tariff = ServiceTariff(
                    tenant_id=tenant_scope.tenant_id,
                    source_tariff_id=int(source_tariff.id),
                    service_kind=source_tariff.service_kind,
                    selector_label=source_tariff.selector_label,
                    estimate_template=source_tariff.estimate_template,
                    short_name=source_tariff.short_name,
                    full_description=source_tariff.full_description,
                    category=source_tariff.category,
                    power_range=source_tariff.power_range,
                    base_price=source_tariff.base_price,
                    included_route_meters=source_tariff.included_route_meters,
                    is_active=source_tariff.is_active,
                    sort_order=source_tariff.sort_order,
                    comment=source_tariff.comment,
                )
                session.add(cloned_tariff)
                await session.flush()
                for source_rule in list(source_tariff.rules or []):
                    mapped_service_id = None
                    if source_rule.service_id is not None:
                        mapped_service_id = service_map.get(int(source_rule.service_id))
                        if mapped_service_id is None:
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=(
                                    "Canonical tariff rule references an inactive "
                                    "service; template was not copied"
                                ),
                            )
                    session.add(
                        ServiceTariffRule(
                            tariff_id=int(cloned_tariff.id),
                            source_rule_id=int(source_rule.id),
                            rule_type=source_rule.rule_type,
                            name=source_rule.name,
                            line_template=source_rule.line_template,
                            unit=source_rule.unit,
                            unit_price=source_rule.unit_price,
                            is_optional=source_rule.is_optional,
                            is_favorite=source_rule.is_favorite,
                            is_active=source_rule.is_active,
                            sort_order=source_rule.sort_order,
                            service_id=mapped_service_id,
                        )
                    )

            for source_rate in source.rates:
                session.add(
                    InstallationRate(
                        tenant_id=tenant_scope.tenant_id,
                        source_installation_rate_id=int(source_rate.id),
                        category=source_rate.category,
                        power_range=source_rate.power_range,
                        base_price=source_rate.base_price,
                        extra_pipe_price=source_rate.extra_pipe_price,
                        included_pipe_meters=source_rate.included_pipe_meters,
                        is_fixed=source_rate.is_fixed,
                        comment=source_rate.comment,
                    )
                )
            if actor_username:
                session.add(
                    TenantAuditEvent(
                        tenant_id=tenant_scope.tenant_id,
                        storefront_id=tenant_scope.storefront_id,
                        actor_username=actor_username,
                        actor_staff_user_id=actor_staff_user_id,
                        action="service_catalog.template_cloned",
                        entity_type="storefront",
                        entity_id=tenant_scope.storefront_id,
                        request_id=current_request_id(),
                        change_set={
                            "source_fingerprint": fingerprint,
                            "cloned_counts": source.counts.model_dump(),
                        },
                    )
                )
            await session.flush()

        return ManagerServiceCatalogCloneResponse(
            status="cloned",
            cloned_counts=source.counts,
            source_fingerprint=fingerprint,
        )
