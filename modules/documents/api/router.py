"""Compatibility composition point for the modular manager document API.

Existing callers import ``modules.documents.api.router.router``. Keep that
public surface stable while each focused router owns one document concern.
The two factory names remain here intentionally: integration tests and runtime
overrides patch them at this historic import path.
"""

from fastapi import APIRouter

from modules.documents.infrastructure.configured_pdf import configured_pdf_converter as _pdf_converter
from services.private_attachment_storage_service import get_private_attachment_storage

from . import (
    amendments,
    draft_parameters,
    condition_presets,
    consumer_defaults,
    facsimiles,
    legal_entities_number_policies,
    managed_document_emails,
    managed_document_readiness,
    managed_document_external_edits,
    managed_documents_artifacts,
    registration_certificates,
    template_external_edits,
    templates_runtime,
    template_audits,
    waybill_composition,
)


router = APIRouter()
router.include_router(amendments.router)
router.include_router(draft_parameters.router)
router.include_router(condition_presets.router)
router.include_router(consumer_defaults.router)
router.include_router(waybill_composition.router)
router.include_router(facsimiles.router)
router.include_router(legal_entities_number_policies.router)
router.include_router(templates_runtime.router)
router.include_router(template_audits.router)
router.include_router(managed_document_emails.router)
router.include_router(template_external_edits.router)
router.include_router(managed_document_external_edits.router)
router.include_router(managed_documents_artifacts.router)
router.include_router(managed_document_readiness.router)
router.include_router(registration_certificates.router)


async def get_google_document_edit_provider(*, session, tenant_scope):
    """Resolve a fail-closed, tenant-bound Google Drive editor."""

    from services.document_drive_connection_service import (
        DocumentDriveConnectionService,
    )

    runtime = await DocumentDriveConnectionService.require_runtime(
        session,
        tenant_scope=tenant_scope,
    )
    return runtime.adapter


__all__ = [
    "router",
    "get_private_attachment_storage",
    "get_google_document_edit_provider",
    "_pdf_converter",
]
