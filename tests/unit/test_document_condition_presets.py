from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from models import DocumentConditionPreset, Tenant
from models.tenancy import TenantScope
from modules.documents.application.condition_presets import (
    ConditionPresetError,
    ConditionPresetNotFound,
    ConditionPresetService,
)


@pytest.mark.asyncio
async def test_condition_presets_are_shared_within_tenant_and_isolated_from_others(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'condition-presets.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Tenant.__table__.create)
        await connection.run_sync(DocumentConditionPreset.__table__.create)

    try:
        async with sessions() as session:
            first = Tenant(slug="first", display_name="First")
            second = Tenant(slug="second", display_name="Second")
            session.add_all([first, second])
            await session.commit()
            await session.refresh(first)
            await session.refresh(second)
            first_scope = TenantScope(int(first.id), 1)
            second_scope = TenantScope(int(second.id), 2)

            preset = await ConditionPresetService.create(
                session, first_scope, "  Леса и альпинисты согласовываются отдельно.  "
            )
            preset_id = int(preset.id)
            assert [item.text for item in await ConditionPresetService.list(session, first_scope)] == [
                "Леса и альпинисты согласовываются отдельно."
            ]
            assert await ConditionPresetService.list(session, second_scope) == []
            second_preset = await ConditionPresetService.create(
                session, second_scope, "Леса и альпинисты согласовываются отдельно."
            )
            second_preset_id = int(second_preset.id)
            with pytest.raises(ConditionPresetError, match="уже сохранено"):
                await ConditionPresetService.create(
                    session, first_scope, "леса  и альпинисты согласовываются отдельно."
                )
            with pytest.raises(ConditionPresetNotFound):
                await ConditionPresetService.delete(session, second_scope, preset_id)
            await ConditionPresetService.delete(session, first_scope, preset_id)
            assert await ConditionPresetService.list(session, first_scope) == []
            assert [item.id for item in await ConditionPresetService.list(session, second_scope)] == [second_preset_id]
    finally:
        await engine.dispose()
