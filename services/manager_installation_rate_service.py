"""Manager-facing projection and limited editing of public installation rates."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import InstallationRate
from schemas_manager_installation_rates import (
    ManagerInstallationRateResponse,
    ManagerInstallationRateSelectionStatus,
    ManagerInstallationRateUpdatePayload,
)
from services.cooling_capacity import power_range_capacity_bounds


class ManagerInstallationRateService:
    """Keeps the Manager projection separate from ServiceTariff estimates."""

    _EQUIPMENT = {
        "wall": ("Настенная сплит-система", "настенной сплит-системы"),
        "duct": ("Канальный кондиционер", "канального кондиционера"),
        "cassette": ("Кассетный кондиционер", "кассетного кондиционера"),
        "ceiling": ("Потолочный кондиционер", "потолочного кондиционера"),
        "multisplit": ("Мульти-сплит-система", "мульти-сплит-системы"),
        "cassette/ceiling": (
            "Кассетный или потолочный кондиционер",
            "кассетного или потолочного кондиционера",
        ),
    }
    _RESOLVABLE_CATEGORIES = frozenset({"wall", "duct", "cassette", "ceiling"})

    @staticmethod
    def _normalized_category(value: str) -> str:
        normalized = str(value or "").strip().lower().replace("_", "-")
        if normalized in {"floor-ceiling", "floor ceiling"}:
            return "ceiling"
        if normalized in {"cassette-ceiling", "cassette/ceiling"}:
            return "cassette/ceiling"
        return normalized

    @staticmethod
    def _format_kw(value: float) -> str:
        return f"{value:g}".replace(".", ",")

    @classmethod
    def _power_label(cls, power_range: str) -> str:
        raw = str(power_range or "").strip()
        if not raw or raw.lower() == "all":
            return "Любая мощность"
        bounds = power_range_capacity_bounds(raw)
        if bounds is None:
            return raw
        lower, upper = bounds
        if lower == upper:
            return f"{cls._format_kw(lower)} кВт"
        return f"{cls._format_kw(lower)}–{cls._format_kw(upper)} кВт"

    @staticmethod
    def _has_resolver_coverage(*, category: str, power_range: str) -> bool:
        normalized_range = str(power_range or "").strip().lower()
        if normalized_range == "all":
            return category != "wall"
        return power_range_capacity_bounds(power_range) is not None

    @classmethod
    def _selection(
        cls, rate: InstallationRate
    ) -> tuple[ManagerInstallationRateSelectionStatus, str]:
        category = cls._normalized_category(rate.category)
        if category == "cassette/ceiling":
            if not rate.is_fixed and cls._has_resolver_coverage(
                category=category,
                power_range=rate.power_range,
            ):
                return (
                    ManagerInstallationRateSelectionStatus.legacy_manual_quote,
                    "Legacy-ставка: применяется только как ручная оценка "
                    "для кассетных и потолочных систем.",
                )
            return (
                ManagerInstallationRateSelectionStatus.unsupported,
                "Фиксированная legacy-ставка не участвует в публичном подборе.",
            )
        if category not in cls._RESOLVABLE_CATEGORIES:
            return (
                ManagerInstallationRateSelectionStatus.unsupported,
                "Эта категория не участвует в автоматическом подборе "
                "публичного checkout.",
            )
        if not cls._has_resolver_coverage(
            category=category,
            power_range=rate.power_range,
        ):
            return (
                ManagerInstallationRateSelectionStatus.unsupported,
                "Диапазон мощности не даёт безопасного правила выбора этого тарифа.",
            )
        if rate.is_fixed:
            return (
                ManagerInstallationRateSelectionStatus.automatic_fixed,
                "Подходит для автоматического расчёта после "
                "безопасного подбора по типу и мощности.",
            )
        return (
            ManagerInstallationRateSelectionStatus.matched_manual_quote,
            "Тариф распознаётся по форм-фактору, но цена "
            "подтверждается после осмотра объекта.",
        )

    @classmethod
    def _to_response(cls, rate: InstallationRate) -> ManagerInstallationRateResponse:
        category = cls._normalized_category(rate.category)
        equipment_label, title_form = cls._EQUIPMENT.get(
            category,
            (
                f"Неподдерживаемая категория: {rate.category}",
                str(rate.category or "оборудования"),
            ),
        )
        selection_status, selection_note = cls._selection(rate)
        return ManagerInstallationRateResponse(
            id=int(rate.id),
            category=rate.category,
            power_range=rate.power_range,
            base_price=int(rate.base_price),
            extra_pipe_price=int(rate.extra_pipe_price),
            included_pipe_meters=int(rate.included_pipe_meters),
            is_fixed=bool(rate.is_fixed),
            comment=rate.comment,
            title=f"Монтаж {title_form}",
            equipment_label=equipment_label,
            power_label=cls._power_label(rate.power_range),
            selection_status=selection_status,
            selection_note=selection_note,
        )

    @classmethod
    async def list_rates(
        cls, session: AsyncSession
    ) -> list[ManagerInstallationRateResponse]:
        result = await session.execute(
            select(InstallationRate).order_by(InstallationRate.id)
        )
        return [cls._to_response(rate) for rate in result.scalars().all()]

    @classmethod
    async def update_rate(
        cls,
        session: AsyncSession,
        *,
        rate_id: int,
        payload: ManagerInstallationRateUpdatePayload,
    ) -> ManagerInstallationRateResponse:
        rate = await session.get(InstallationRate, rate_id)
        if rate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Installation rate not found",
            )

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(
                rate,
                field,
                value.strip() if field == "comment" and value is not None else value,
            )
        session.add(rate)
        await session.commit()
        await session.refresh(rate)
        return cls._to_response(rate)
