"""MCP adapters to the released maintenance domain, with common audit/receipts."""
import asyncio
import base64
from uuid import NAMESPACE_URL, uuid5

from mcp.types import CallToolResult, ImageContent, TextContent
from api_contracts.maintenance_observations import CreateMaintenanceObservation, PrepareMaintenanceDefectAct
from api_contracts.maintenance_offers import PrepareMaintenanceOffer
from core.config import settings
from models import DocumentLegalEntity
from schemas_connector_maintenance import (
    ConnectorDefectActResult, ConnectorFindingResult, ConnectorOfferResult,
    ConnectorPhotoReadResult, ConnectorPhotoResult,
)
from services.authenticated_command_service import AuthenticatedCommandService
from services.connector_file_service import ConnectorFileService
from services.equipment_service import EquipmentService
from services.maintenance_observation_service import MaintenanceObservationService as Findings, ObservationNotFound
from services.maintenance_offer_service import MaintenanceOfferService as Offers
from services.public_write_idempotency_service import PublicWriteCommandResponse


def manager_link(order_id):
    return f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/kanban?orderId={order_id}"


class ConnectorMaintenanceService:
    @classmethod
    async def read(cls, session, actor, name, inputs):
        values = inputs.model_dump()
        scope = actor.tenant_scope
        if name == "list_equipment":
            result = await EquipmentService.list_equipment(session, **values, q=None, attention=None, tenant_scope=scope)
            if result is None:
                raise ObservationNotFound("Customer not found")
            return result
        if name == "get_equipment":
            result = await EquipmentService.get_equipment_detail(session, **values, history_limit=1, tenant_scope=scope)
            if result is None:
                raise ObservationNotFound("Equipment not found")
            return result
        if name == "list_equipment_history":
            result = await EquipmentService.list_history(session, **values, tenant_scope=scope)
            if result is None:
                raise ObservationNotFound("Equipment not found")
            return result
        if name == "list_maintenance_findings":
            return await Findings.list(session, **values, scope=scope)
        if name in {"get_maintenance_finding", "get_maintenance_finding_photo"}:
            observation = await Findings.get(session, inputs.observation_id, scope)
            detail = await Findings.detail(session, observation, scope)
            if name == "get_maintenance_finding":
                return detail
            if inputs.attachment_id not in {photo.id for photo in detail.photos}:
                raise ObservationNotFound("Photo not found on this finding")
            from services.service_attachment_service import ServiceAttachmentService
            try:
                attachment, content, mime = await ServiceAttachmentService.read_variant(
                    session, attachment_id=inputs.attachment_id, variant="preview")
            except FileNotFoundError:
                raise ObservationNotFound("Photo not available") from None
            # Storage I/O may take time: recheck live source access before
            # returning private bytes, rather than relying on an earlier read.
            await Findings.get(session, inputs.observation_id, scope)
            if len(content) > min(20 * 1024 * 1024, settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES):
                raise ValueError("Photo exceeds the configured size limit")
            detected = await asyncio.to_thread(ConnectorFileService.validate_image, content)
            if detected != mime:
                raise ValueError("Photo content type changed")
            result = ConnectorPhotoReadResult(observation_id=observation.id, attachment_id=attachment.id,
                mime_type=mime, variant="preview" if attachment.preview_storage_key else "original",
                manager_url=manager_link(observation.source_order_id)).model_dump(mode="json")
            return CallToolResult(content=[TextContent(type="text", text="Private photo from this maintenance finding"),
                ImageContent(type="image", data=base64.b64encode(content).decode(), mimeType=mime)],
                structuredContent=result, isError=False)
        values["source_order_id"] = values.pop("order_id")
        if name == "list_maintenance_defect_acts":
            from modules.documents.application.maintenance_act_preparation import MaintenanceActPreparationService
            return await MaintenanceActPreparationService.list(session, **values, scope=scope)
        if name == "list_maintenance_offers":
            result = await Offers.list(session, **values, scope=scope)
            result.update(await Offers.available_proposals(session, **values, scope=scope),
                          manager_url=manager_link(inputs.order_id))
            return result
        raise ValueError("Unknown maintenance read")

    @classmethod
    async def write(cls, session, actor, name, inputs):
        scope = actor.tenant_scope
        request = inputs.model_dump(mode="json", exclude={"idempotency_key"})
        # Check current resource access even on receipt replay; a durable receipt
        # never restores a moved/foreign source or withdrawn continuation.
        if hasattr(inputs, "observation_id"):
            finding = await Findings.get(session, inputs.observation_id, scope)
            source_order_id = finding.source_order_id
        else:
            source_order_id = inputs.order_id
            await Offers.context(session, source_order_id, scope)
        if name == "upload_maintenance_finding_photo":
            ConnectorFileService.validate_source(inputs.file)
            # Temporary credentials may refresh. The immutable ChatGPT file ID
            # and its supplied metadata define the intended source across retries.
            request["file"].pop("download_url")
        if name == "prepare_maintenance_defect_act":
            issuer = await session.get(DocumentLegalEntity, inputs.payload.legal_entity_id)
            if issuer is None or issuer.tenant_id != scope.tenant_id or issuer.status != "active":
                raise ObservationNotFound("Active legal entity not found")
        command_key = uuid5(NAMESPACE_URL, f"kitlane:{actor.staff_user_id}:{name}:{inputs.idempotency_key}")
        model = {"create_maintenance_finding": ConnectorFindingResult,
                 "update_maintenance_finding": ConnectorFindingResult,
                 "upload_maintenance_finding_photo": ConnectorPhotoResult,
                 "prepare_maintenance_defect_act": ConnectorDefectActResult,
                 "prepare_maintenance_offer": ConnectorOfferResult}[name]

        async def operation():
            common = dict(actor=actor.username, scope=scope)
            if name == "create_maintenance_finding":
                payload = CreateMaintenanceObservation.model_validate({**inputs.payload.model_dump(), "command_key": command_key})
                value = await Findings.create(session, order_id=source_order_id, payload=payload,
                                               **common, commit=False, origin="chatgpt_maintenance")
                value = value.model_dump()
            elif name == "update_maintenance_finding":
                value = await Findings.update(session, observation_id=inputs.observation_id,
                                               payload=inputs.payload, **common, commit=False)
                value = value.model_dump()
            elif name == "upload_maintenance_finding_photo":
                content, filename, mime = await ConnectorFileService.download(inputs.file)
                value = await Findings.upload_photo(session, observation_id=inputs.observation_id,
                    key=command_key, content=content, filename=filename, mime_type=mime, **common,
                    commit=False, source="chatgpt_maintenance", source_meta={"chatgpt_file_id": inputs.file.file_id})
                value = dict(value) if isinstance(value, dict) else value.model_dump()
                value["observation_id"] = inputs.observation_id
            elif name == "prepare_maintenance_defect_act":
                from modules.documents.application.maintenance_act_preparation import MaintenanceActPreparationService
                from modules.documents.infrastructure.template_source_storage import PrivateTemplateSourceStorage
                from services.private_attachment_storage_service import get_private_attachment_storage
                payload = PrepareMaintenanceDefectAct.model_validate({**inputs.payload.model_dump(), "command_key": command_key})
                value = await MaintenanceActPreparationService.prepare(session, source_order_id=source_order_id,
                    payload=payload, **common, storage=PrivateTemplateSourceStorage(get_private_attachment_storage()))
            else:
                payload = PrepareMaintenanceOffer.model_validate({**inputs.payload.model_dump(), "command_key": command_key})
                value = await Offers.prepare(session, source_order_id=source_order_id, payload=payload, **common)
            # Domain detail may contain growing revisions/photos. Persist only
            # the declared compact response, not those extra detail fields.
            value = model.model_validate({**{key: value[key] for key in model.model_fields if key in value},
                                          "manager_url": manager_link(source_order_id)})
            resource_id = value.document_id if name == "prepare_maintenance_defect_act" else value.id
            resource_type = "maintenance_photo" if name == "upload_maintenance_finding_photo" else "maintenance_act" if name == "prepare_maintenance_defect_act" else "maintenance_offer" if name == "prepare_maintenance_offer" else "maintenance_finding"
            return PublicWriteCommandResponse(value=value, resource_type=resource_type, resource_id=resource_id,
                                               response_max_bytes=256 * 1024)

        return await AuthenticatedCommandService.execute(session, actor=actor,
            command_name={"create_maintenance_finding": "maintenance.finding.create",
                          "update_maintenance_finding": "maintenance.finding.update",
                          "upload_maintenance_finding_photo": "maintenance.photo.upload",
                          "prepare_maintenance_defect_act": "maintenance.act.prepare",
                          "prepare_maintenance_offer": "maintenance.offer.prepare"}[name],
            idempotency_key=inputs.idempotency_key, payload=request, response_model=model, operation=operation)
