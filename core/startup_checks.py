"""Fail-closed checks for production processes before they accept work."""

from typing import Any


async def run_production_startup_checks(current_settings: Any) -> None:
    if not current_settings.is_production:
        return

    from services.private_attachment_storage_service import (
        verify_private_attachment_storage_startup,
    )

    await verify_private_attachment_storage_startup(current_settings)
