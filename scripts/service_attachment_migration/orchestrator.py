"""Transaction boundary and reporting for the service-attachment migration."""

from __future__ import annotations

from sqlalchemy import inspect, text

from core.database import async_session_maker, engine
from services.private_attachment_storage_service import get_private_attachment_storage
from services.tenant_scope_service import SystemTenantScopeResolver

from .attachment_copy import migrate_attachments
from .equipment_backfill import migrate_equipment_links, migrate_legacy_coverages
from .legacy_sources import MigrationStats


async def run(
    *,
    execute: bool,
    order_id: int | None,
    allow_partial: bool = False,
) -> MigrationStats:
    required_tables = {
        "service_attachment",
        "order_attachment_link",
        "equipment_attachment_link",
        "equipment_order_link",
        "equipment_warranty_coverage",
    }
    async with engine.connect() as connection:
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )
    missing_tables = sorted(required_tables - table_names)
    if missing_tables:
        raise RuntimeError(
            "Database schema is not ready for this migration. Run 'alembic upgrade head' first. "
            f"Missing tables: {', '.join(missing_tables)}"
        )

    try:
        storage = get_private_attachment_storage()
        if execute:
            await storage.verify_writable()
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(f"Private attachment storage preflight failed: {exc}") from exc

    stats = MigrationStats()
    async with async_session_maker() as session:
        tenant_scope = await SystemTenantScopeResolver.resolve(session)
        if execute and session.get_bind().dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"),
                {"lock_key": 0x4D564E4154544143},
            )
        await migrate_attachments(
            session,
            execute=execute,
            order_id=order_id,
            stats=stats,
            storage=storage,
            tenant_scope=tenant_scope,
        )
        await migrate_equipment_links(
            session,
            execute=execute,
            order_id=order_id,
            stats=stats,
        )
        await migrate_legacy_coverages(
            session,
            execute=execute,
            order_id=order_id,
            stats=stats,
        )
        if execute:
            if stats.transient_failures or stats.configuration_failures:
                await session.rollback()
                raise RuntimeError(
                    "Attachment migration stopped because download/configuration failures require a retry. "
                    "Run dry-run and review the per-file report first."
                )
            if not allow_partial and (
                stats.attachments_unavailable or stats.equipment_link_conflicts
            ):
                await session.rollback()
                raise RuntimeError(
                    "Migration found unavailable attachments or conflicting equipment links and rolled back. "
                    "Resolve the report first, or explicitly use --allow-partial after accepting the gaps."
                )
            await session.commit()
        else:
            await session.rollback()
    return stats


def print_report(stats: MigrationStats, *, execute: bool) -> None:
    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"Service attachment migration: {mode}")
    for key, value in stats.__dict__.items():
        if key == "issues":
            continue
        print(f"  {key}: {value}")
    if stats.issues:
        print("  issues:")
        for issue in stats.issues:
            print(f"    - {issue}")
    if not execute:
        print(f"  attachments_ready_for_execute: {stats.attachments_verified}")
        print("No data changed. Re-run with --execute after reviewing this report.")
    else:
        print("Legacy JSON, public copies and legacy warranty fields were preserved for audit.")
        print("Public cleanup is a separate step after private-copy verification and sign-off.")
