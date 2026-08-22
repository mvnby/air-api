from datetime import datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from models.tenancy import TenantScope
from services.dashboard_marketing import MarketingSnapshot
from services.dashboard_overview_service import (
    DashboardOverviewService,
    current_month_window,
    delta_and_trend,
)


def test_current_month_window_includes_previous_calendar_month():
    window = current_month_window(
        datetime(2026, 1, 17, 12, 30, tzinfo=ZoneInfo("Europe/Minsk"))
    )

    assert window.current_start.isoformat() == "2026-01-01T00:00:00+03:00"
    assert window.current_end.isoformat() == "2026-02-01T00:00:00+03:00"
    assert window.previous_start.isoformat() == "2025-12-01T00:00:00+03:00"
    assert window.previous_end == window.current_start


@pytest.mark.parametrize(
    ("current", "previous", "expected_delta", "expected_trend"),
    [
        (120.0, 100.0, 20.0, "up"),
        (80.0, 100.0, -20.0, "down"),
        (100.0, 100.0, 0.0, "flat"),
        (10.0, 0.0, None, "up"),
        (0.0, 0.0, None, "flat"),
        (10.0, None, None, "unavailable"),
    ],
)
def test_delta_and_trend_handles_zero_division(
    current,
    previous,
    expected_delta,
    expected_trend,
):
    assert delta_and_trend(current, previous) == (expected_delta, expected_trend)


@pytest.mark.asyncio
async def test_dashboard_marketing_is_fail_soft():
    provider = AsyncMock()
    provider.get_snapshot.side_effect = RuntimeError("provider secret must not leak")
    service = DashboardOverviewService(marketing_provider=provider)

    result = await service._safe_marketing(
        None,
        TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        start=datetime(2026, 8, 1).date(),
        end_exclusive=datetime(2026, 8, 2).date(),
    )

    assert result == MarketingSnapshot(
        status="error",
        message="Yandex Metrika is temporarily unavailable.",
    )
