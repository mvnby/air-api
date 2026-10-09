"""Observe stable Drive versions and adopt individual proposals atomically."""

import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import defer
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models.call_recording import CallAdoption, CallDriveConnection, CallProposal, CallRecording
from schemas_call_recordings import CallAdoptionResponse, CallRecordingResponse, CallProposalResponse, CallRecordingListResponse, CallPollResponse
from schemas_incoming import IncomingCreatePayload
from services.call_drive_connection_service import CallDriveConnectionService, require_live_call_actor
from services.call_drive_provider import CallDriveError, MAX_CALL_BYTES
from services.call_recording_structure import call_requested_time, samsung_call_time
from services.command_transaction import command_transaction
from services.incoming_command_service import IncomingCommandService
from services.personal_task_service import PersonalTaskService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict
from core.input_validation import validate_optional_phone

CALL_EVENT_TYPE = "call.recording_process.v1"
STABILITY_SECONDS = 60
MAX_DAILY_RECORDINGS = 20


def source_version(metadata: dict) -> str:
    return hashlib.sha256(f"{metadata.get('headRevisionId', '')}:{metadata.get('version', '')}:{metadata.get('md5Checksum', '')}:{metadata.get('size', '')}".encode()).hexdigest()


def validate_source(metadata: dict, folder_id: str) -> None:
    if metadata.get("trashed") or folder_id not in metadata.get("parents", []):
        raise CallDriveError("call_file_outside_folder", "Запись недоступна в выбранной папке", status_code=409)
    mime = str(metadata.get("mimeType") or "").lower()
    if not (mime.startswith("audio/") or mime in {"video/3gpp", "video/mp4", "application/ogg"}):
        raise CallDriveError("call_file_not_audio", "Файл требует ручной проверки формата", status_code=422)
    if not metadata.get("md5Checksum") or not metadata.get("version") or not metadata.get("modifiedTime"):
        raise CallDriveError("call_upload_incomplete", "Файл ещё не готов к обработке", status_code=409)
    size = int(metadata.get("size") or 0)
    if not 0 < size <= MAX_CALL_BYTES:
        raise CallDriveError("call_audio_too_large", "Запись пустая или больше 10 МБ")


class CallRecordingService:
    @staticmethod
    async def enqueue(session, row):
        from services.communications.outbox_service import IntegrationOutboxService
        event = await IntegrationOutboxService.enqueue(session, event_type=CALL_EVENT_TYPE, aggregate_type="call_recording", aggregate_id=row.id, payload={"recording_id": row.id, "connection_id": row.connection_id}, idempotency_key=f"call-recording:{row.id}", max_attempts=9, priority=40)
        row.job_event_id = event.event_id
        row.state = "queued"
        session.add(row)
        return event

    @classmethod
    async def poll(cls, session, actor, *, file_id=None, provider=None, now=None):
        CallDriveConnectionService.require_enabled()
        await require_live_call_actor(session, actor, write=True)
        adapter = await CallDriveConnectionService.adapter(session, actor, provider=provider)
        connection = await CallDriveConnectionService.get(session, actor)
        folder_id = connection.folder_id
        if not folder_id:
            raise CallDriveError("call_folder_not_selected", "Выберите папку с записями", status_code=409)
        if file_id:
            files, next_page = [await adapter.metadata(file_id)], None
        else:
            files, next_page = await adapter.list_recordings(folder_id, page_token=connection.page_token)
        # Serialize observation and enqueue across HA nodes and browser retries.
        connection = await CallDriveConnectionService.get(session, actor, for_update=True)
        if connection.folder_id != folder_id:
            raise CallDriveError("call_folder_changed", "Папка изменилась, повторите проверку", status_code=409)
        now = now or datetime.now(timezone.utc)
        daily = await session.scalar(select(func.count()).select_from(CallRecording).where(CallRecording.connection_id == connection.id, CallRecording.created_at >= now - timedelta(days=1)))
        queued, observed = 0, 0
        for metadata in files[:5]:
            try:
                validate_source(metadata, folder_id)
            except CallDriveError:
                if file_id:
                    raise
                continue
            modified = datetime.fromisoformat(metadata["modifiedTime"].replace("Z", "+00:00"))
            version = source_version(metadata)
            row = await session.scalar(select(CallRecording).where(CallRecording.connection_id == connection.id, CallRecording.file_id == metadata["id"], CallRecording.source_version == version))
            if row is None:
                if daily >= MAX_DAILY_RECORDINGS:
                    continue
                call_time = samsung_call_time(metadata["name"])
                row = CallRecording(connection_id=connection.id, file_id=metadata["id"], source_version=version, source_checksum=metadata["md5Checksum"], source_size=int(metadata["size"]), source_url=f"https://drive.google.com/file/d/{metadata['id']}/view", filename=str(metadata["name"])[:300], mime_type=metadata["mimeType"], source_modified_at=modified, call_occurred_at=call_time, time_source="samsung_filename" if call_time else "unknown", observed_at=now, created_at=now)
                prior = await session.scalar(select(CallRecording).where(CallRecording.connection_id == connection.id, CallRecording.file_id == row.file_id, CallRecording.source_checksum == row.source_checksum).order_by(CallRecording.id.desc()).limit(1))
                if prior:
                    # A metadata-only revision needs fresh source-clock review,
                    # but identical bytes reuse successful paid checkpoints.
                    row.transcript, row.structure = prior.transcript, prior.structure
                    row.transcription_provider, row.transcription_model = prior.transcription_provider, prior.transcription_model
                    row.downloaded_audio = prior.downloaded_audio
                    row.audio_duration_seconds = prior.audio_duration_seconds
                session.add(row)
                await session.flush()
                daily += 1
            elif row.state == "observing":
                row.observations += 1
                if now - row.observed_at >= timedelta(seconds=STABILITY_SECONDS) and now - modified >= timedelta(seconds=STABILITY_SECONDS):
                    await cls.enqueue(session, row)
                    queued += 1
            observed += 1
        connection.last_polled_at = now
        if not file_id:
            connection.page_token = next_page
        session.add(connection)
        await session.commit()
        return CallPollResponse(observed=observed, queued=queued, has_more=bool(next_page))

    @staticmethod
    async def get_row(session, actor, recording_id, *, for_update=False):
        await require_live_call_actor(session, actor)
        statement = select(CallRecording).join(CallDriveConnection).where(CallRecording.id == recording_id, CallDriveConnection.staff_user_id == actor.staff_user_id, CallDriveConnection.tenant_id == actor.tenant_scope.tenant_id, CallDriveConnection.storefront_id == actor.tenant_scope.storefront_id).execution_options(populate_existing=True)
        if for_update:
            statement = statement.with_for_update(of=CallRecording)
        row = await session.scalar(statement)
        if row is None:
            raise LookupError("Запись не найдена")
        return row

    @staticmethod
    def resource_url(resource_type, resource_id):
        path = f"leads?incomingId={resource_id}" if resource_type == "lead" else f"tasks?taskId={resource_id}"
        return f"{settings.MANAGER_BASE_URL.rstrip('/')}/{path}"

    @classmethod
    async def project(cls, session, row, *, detailed=False):
        values = {field: getattr(row, field) for field in CallRecordingResponse.model_fields if field not in {"proposals", "transcript", "structure"}}
        if detailed:
            values.update(transcript=row.transcript, structure=row.structure)
            proposals = list((await session.scalars(select(CallProposal).where(CallProposal.recording_id == row.id).order_by(CallProposal.id))).all())
            receipts = list((await session.scalars(select(CallAdoption).where(CallAdoption.connection_id == row.connection_id, CallAdoption.file_id == row.file_id))).all())
            accepted = {receipt.action_key: receipt for receipt in receipts}
            values["proposals"] = []
            for proposal in proposals:
                receipt = accepted.get(proposal.action_key)
                payload = proposal.payload
                if receipt:
                    payload = receipt.payload.get("incoming" if proposal.kind == "incoming" else "task") or proposal.payload
                desired_at, precision = None, None
                if proposal.kind == "incoming":
                    if receipt:
                        from models import Lead
                        lead = await session.get(Lead, receipt.resource_id)
                        meta = (lead.intake_meta or {}) if lead else {}
                        desired_at = datetime.fromisoformat(meta["requested_at"]) if meta.get("requested_at") else None
                        precision = meta.get("date_precision")
                    elif payload.get("requested_at"):
                        desired_at, precision = datetime.fromisoformat(payload["requested_at"]), "datetime"
                    else:
                        desired_at, precision, _ = call_requested_time(payload.get("requested_time_text"), row.call_occurred_at)
                values["proposals"].append(CallProposalResponse(id=proposal.id, kind=proposal.kind, payload=payload, evidence=proposal.evidence, needs_clarification=proposal.needs_clarification, requested_date=desired_at.astimezone(ZoneInfo("Europe/Minsk")).date() if desired_at else None, date_precision=precision, accepted_resource_type=receipt.resource_type if receipt else None, accepted_resource_id=receipt.resource_id if receipt else None, accepted_url=cls.resource_url(receipt.resource_type, receipt.resource_id) if receipt else None))
        return CallRecordingResponse(**values)

    @classmethod
    async def get(cls, session, actor, recording_id):
        return await cls.project(session, await cls.get_row(session, actor, recording_id), detailed=True)

    @classmethod
    async def list(cls, session, actor, *, limit=50, offset=0):
        await require_live_call_actor(session, actor)
        criteria = (CallDriveConnection.staff_user_id == actor.staff_user_id, CallDriveConnection.tenant_id == actor.tenant_scope.tenant_id, CallDriveConnection.storefront_id == actor.tenant_scope.storefront_id)
        total = await session.scalar(select(func.count()).select_from(CallRecording).join(CallDriveConnection).where(*criteria))
        rows = (await session.scalars(select(CallRecording).options(defer(CallRecording.downloaded_audio, raiseload=True), defer(CallRecording.transcript, raiseload=True), defer(CallRecording.structure, raiseload=True)).join(CallDriveConnection).where(*criteria).order_by(CallRecording.created_at.desc(), CallRecording.id.desc()).offset(offset).limit(min(100, limit)))).all()
        return CallRecordingListResponse(items=[await cls.project(session, row) for row in rows], total=total)

    @classmethod
    async def metadata(cls, session, actor, recording_id, payload):
        await require_live_call_actor(session, actor, write=True)
        row = await cls.get_row(session, actor, recording_id, for_update=True)
        if row.version != payload.expected_version or row.state in {"processing", "queued"}:
            raise CallDriveError("call_version_conflict", "Запись изменилась или обрабатывается", status_code=409)
        row.phone = validate_optional_phone(payload.phone)
        row.call_occurred_at = payload.call_occurred_at
        row.time_source = "manual" if payload.call_occurred_at else "unknown"
        if row.structure:
            # Metadata corrections must explicitly rebuild proposals at retry.
            # The paid structured extraction is kept and reused.
            row.state, row.stage = "failed", "proposals"
            row.last_error_code = "call_metadata_changed"
        row.version += 1
        session.add(row)
        await session.commit()
        return await cls.get(session, actor, recording_id)

    @classmethod
    async def retry(cls, session, actor, recording_id, payload):
        CallDriveConnectionService.require_enabled()
        await require_live_call_actor(session, actor, write=True)
        row = await cls.get_row(session, actor, recording_id, for_update=True)
        if row.version != payload.expected_version or row.state not in {"failed", "reconnect_required", "manual_review"}:
            raise CallDriveError("call_retry_conflict", "Повтор недоступен для текущей версии", status_code=409)
        if row.stage_attempts.get(row.stage, 0) >= 3:
            raise CallDriveError("call_stage_exhausted", "Лимит попыток этапа исчерпан: разберите запись вручную", status_code=409)
        if row.job_event_id:
            from models import IntegrationOutboxEvent
            event = await session.get(IntegrationOutboxEvent, row.job_event_id, with_for_update=True)
            if event.status == "processing" and event.lease_expires_at and event.lease_expires_at > datetime.now(timezone.utc):
                raise CallDriveError("call_job_busy", "Запись ещё обрабатывается", status_code=409)
            event.status, event.available_at = "pending", datetime.now(timezone.utc)
            event.worker_id = event.lease_token = event.lease_expires_at = None
            session.add(event)
        else:
            await cls.enqueue(session, row)
        row.state, row.last_error_code = "queued", None
        row.version += 1
        session.add(row)
        await session.commit()
        return await cls.get(session, actor, recording_id)

    @classmethod
    async def adopt(cls, session, actor, recording_id, proposal_id, payload):
        async with command_transaction(session):
            await require_live_call_actor(session, actor, write=True)
            # One owner lock serializes adoptions even across changed versions.
            await CallDriveConnectionService.get(session, actor, for_update=True)
            row = await cls.get_row(session, actor, recording_id, for_update=True)
            proposal = await session.scalar(select(CallProposal).where(CallProposal.id == proposal_id, CallProposal.recording_id == row.id))
            if proposal is None:
                raise LookupError("Предложение не найдено")
            receipt = await session.scalar(select(CallAdoption).where(CallAdoption.connection_id == row.connection_id, CallAdoption.file_id == row.file_id, CallAdoption.action_key == proposal.action_key))
            request = payload.model_dump(mode="json", exclude={"expected_version"})
            if receipt:
                if receipt.payload != request:
                    raise PublicWriteIdempotencyConflict("Действие уже принято с другими данными: измените сохранённое входящее или поручение")
                return CallAdoptionResponse(resource_type=receipt.resource_type, resource_id=receipt.resource_id, resource_url=cls.resource_url(receipt.resource_type, receipt.resource_id), replayed=True)
            if row.state != "ready_for_review" or row.version != payload.expected_version:
                raise CallDriveError("call_version_conflict", "Перечитайте результат обработки", status_code=409)
            trusted_actor = CommandActor(actor.staff_user_id, actor.username, actor.tenant_scope, "drive_call")
            stable_key = hashlib.sha256(f"call:{row.connection_id}:{row.file_id}:{proposal.action_key}".encode()).hexdigest()
            if proposal.kind == "incoming":
                if payload.incoming is None or payload.task is not None:
                    raise ValueError("Нужны только поля выбранного входящего")
                data = payload.incoming.model_dump(mode="json")
                if data["requested_at"] is None:
                    parsed, precision, date_text = call_requested_time(data["requested_time_text"], row.call_occurred_at)
                    if parsed and precision == "date":
                        # Let the shared incoming contract derive a day with
                        # date precision instead of passing midnight as an hour.
                        data["requested_time_text"] = date_text
                outcome = await IncomingCommandService.create(session, actor=trusted_actor, payload=IncomingCreatePayload(**data, source_occurred_at=row.call_occurred_at, source_timezone="Europe/Minsk", source_event_id=f"drive-call:{stable_key}"), idempotency_key=stable_key)
                resource_type, resource_id = "lead", outcome.value.lead_id
                from models import Lead
                lead = await session.get(Lead, resource_id)
                lead.intake_meta = {**lead.intake_meta, "requested_time_text": payload.incoming.requested_time_text, "source_url": row.source_url, "source_file_id": row.file_id, "source_checksum": row.source_checksum, "source_version": row.source_version, "source_recording_id": row.id}
                session.add(lead)
            else:
                if payload.task is None or payload.incoming is not None:
                    raise ValueError("Нужны только поля выбранного поручения")
                task = payload.task.model_copy(update={"description": f"{payload.task.description or ''}\nЗапись звонка: {row.source_url}"})
                outcome = await PersonalTaskService.create(session, actor=trusted_actor, payload=task, idempotency_key=stable_key)
                resource_type, resource_id = "personal_task", outcome.value.id
            session.add(CallAdoption(connection_id=row.connection_id, file_id=row.file_id, action_key=proposal.action_key, proposal_id=proposal_id, resource_type=resource_type, resource_id=resource_id, payload=request))
            await session.flush()
            return CallAdoptionResponse(resource_type=resource_type, resource_id=resource_id, resource_url=cls.resource_url(resource_type, resource_id))
