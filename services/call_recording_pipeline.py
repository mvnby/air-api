"""Lease-fenced checkpoints; speech and structured extraction retry separately."""

import hashlib
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models import IntegrationOutboxEvent, StaffUser
from models.call_recording import CallAdoption, CallDriveConnection, CallProposal, CallRecording
from models.tenancy import TenantScope
from services.bot_voice_transcription_provider import BotVoiceTranscriptionProvider
from services.call_drive_connection_service import CallDriveConnectionService, require_live_call_actor
from services.call_drive_provider import CallDriveError
from services.call_recording_audio import normalize_call_audio
from services.call_recording_service import source_version, validate_source
from services.call_recording_structure import ExtractedCall, action_proposals, extract_call


class CallLeaseLost(RuntimeError):
    code = "call_lease_lost"


class CallTranscriptionPending(RuntimeError):
    """A saved Google operation is still running; this is not a failed attempt."""
    code = "call_google_pending"


def google_audio_source_id(snapshot):
    return hashlib.sha256(f"call:{snapshot['id']}:{snapshot['connection_id']}:{snapshot['source_checksum']}".encode()).hexdigest()


async def fenced_recording(session, claim):
    event = await session.scalar(select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.event_id == claim.event_id, IntegrationOutboxEvent.status == "processing", IntegrationOutboxEvent.lease_token == claim.lease_token, IntegrationOutboxEvent.worker_id == claim.worker_id, IntegrationOutboxEvent.lease_expires_at > datetime.now(timezone.utc)).with_for_update())
    if event is None:
        raise CallLeaseLost()
    row = await session.get(CallRecording, claim.recording_id, with_for_update=True, populate_existing=True)
    if row is None or row.connection_id != claim.connection_id:
        raise CallLeaseLost()
    return row


class CallRecordingPipeline:
    @classmethod
    async def run(cls, *, claim, session_factory, provider=None, normalizer=None, transcriber=None, extractor=None):
        CallDriveConnectionService.require_enabled()
        normalizer = normalizer or normalize_call_audio
        injected_transcriber = transcriber is not None
        transcriber = transcriber or cls.transcribe
        extractor = extractor or extract_call
        async with session_factory() as session:
            row = await fenced_recording(session, claim)
            connection = await session.get(CallDriveConnection, claim.connection_id)
            user = await session.get(StaffUser, connection.staff_user_id)
            actor = CommandActor(connection.staff_user_id, user.username or str(user.id), TenantScope(connection.tenant_id, connection.storefront_id), "drive_call")
            await require_live_call_actor(session, actor, write=True)
            if row.state == "ready_for_review":
                return
            await session.rollback()

        while True:
            async with session_factory() as session:
                row = await fenced_recording(session, claim)
                await require_live_call_actor(session, actor, write=True)
                if row.structure is not None:
                    row.stage = "proposals"
                elif row.transcript is not None:
                    row.stage = "structure"
                elif row.downloaded_audio is not None:
                    row.stage = "transcribe"
                else:
                    row.stage = "download"
                stage = row.stage
                attempts = dict(row.stage_attempts)
                connection = await session.get(CallDriveConnection, claim.connection_id, populate_existing=True)
                if not connection.encrypted_credentials:
                    raise CallDriveError("call_drive_not_connected", "Подключение записей отключено", status_code=409)
                if stage == "transcribe" and row.transcription_provider is None:
                    row.transcription_provider = connection.transcription_provider
                    row.transcription_model = settings.CALL_RECORDINGS_GOOGLE_MODEL if row.transcription_provider == "google_batch" else settings.CALL_RECORDINGS_TRANSCRIPTION_MODEL
                polling_google = stage == "transcribe" and row.transcription_provider == "google_batch" and row.transcription_operation is not None
                if stage != "proposals" and not polling_google:
                    if attempts.get(stage, 0) >= 3:
                        raise CallDriveError("call_stage_exhausted", "Лимит попыток этапа исчерпан")
                    attempts[stage] = attempts.get(stage, 0) + 1
                row.stage_attempts = attempts
                row.state, row.last_error_code = "processing", None
                row.version += 1
                row.updated_at = datetime.now(timezone.utc)
                snapshot = row.model_dump()
                selected_folder = connection.folder_id
                session.add(row)
                await session.commit()

            # No database connection is held during provider calls.
            if stage == "download":
                async with session_factory() as session:
                    adapter = await CallDriveConnectionService.adapter(session, actor, provider=provider)
                metadata = await adapter.metadata(snapshot["file_id"])
                validate_source(metadata, selected_folder)
                if source_version(metadata) != snapshot["source_version"]:
                    raise CallDriveError("call_source_changed", "Запись изменилась: проверьте папку повторно", status_code=409)
                content = await adapter.download_audio(snapshot["file_id"])
                if len(content) != snapshot["source_size"] or hashlib.md5(content).hexdigest() != snapshot["source_checksum"]:
                    raise CallDriveError("call_upload_changed", "Загрузка ещё не закончена или файл изменился", status_code=409)
                after = await adapter.metadata(snapshot["file_id"])
                validate_source(after, selected_folder)
                if source_version(after) != snapshot["source_version"]:
                    raise CallDriveError("call_source_changed", "Запись изменилась при скачивании", status_code=409)
                result = await normalizer(content=content, filename=snapshot["filename"], mime_type=snapshot["mime_type"])
            elif stage == "transcribe":
                if snapshot["transcription_provider"] == "google_batch" and not injected_transcriber:
                    from services.call_google_batch_transcription import GoogleCallBatchTranscriptionProvider
                    source_id = google_audio_source_id(snapshot)
                    if snapshot["transcription_operation"] is None:
                        operation = await GoogleCallBatchTranscriptionProvider.submit(content=snapshot["downloaded_audio"], source_id=source_id)
                        async with session_factory() as session:
                            row = await fenced_recording(session, claim)
                            await require_live_call_actor(session, actor, write=True)
                            connection = await session.get(CallDriveConnection, claim.connection_id, populate_existing=True)
                            if not connection.encrypted_credentials or connection.folder_id != selected_folder:
                                raise CallDriveError("call_connection_changed", "Подключение или папка изменились", status_code=409)
                            row.transcription_operation = operation
                            row.transcription_submitted_at = datetime.now(timezone.utc)
                            row.version += 1
                            session.add(row)
                            await session.commit()
                        raise CallTranscriptionPending()
                    submitted_at = snapshot["transcription_submitted_at"]
                    if submitted_at is None or datetime.now(timezone.utc) - submitted_at > timedelta(hours=26):
                        raise CallDriveError("call_google_wait_expired", "Google не завершил распознавание в пределах срока")
                    result = await GoogleCallBatchTranscriptionProvider.poll(operation_name=snapshot["transcription_operation"], source_id=source_id)
                    if result is None:
                        raise CallTranscriptionPending()
                else:
                    result = await transcriber(content=snapshot["downloaded_audio"], filename="recording.wav", mime_type="audio/wav")
            elif stage == "structure":
                result = await extractor(transcript=snapshot["transcript"], call_occurred_at=snapshot["call_occurred_at"])
                result = result if isinstance(result, ExtractedCall) else ExtractedCall.model_validate(result)
            else:
                result = action_proposals(ExtractedCall.model_validate(snapshot["structure"]), transcript=snapshot["transcript"], call_occurred_at=snapshot["call_occurred_at"], manual_phone=snapshot["phone"])

            async with session_factory() as session:
                row = await fenced_recording(session, claim)
                await require_live_call_actor(session, actor, write=True)
                connection = await session.get(CallDriveConnection, claim.connection_id, populate_existing=True)
                if not connection.encrypted_credentials or connection.folder_id != selected_folder:
                    raise CallDriveError("call_connection_changed", "Подключение или папка изменились", status_code=409)
                if stage == "download":
                    row.downloaded_audio = result.content
                    row.audio_duration_seconds = result.detected_duration_seconds
                    row.stage = "transcribe"
                elif stage == "transcribe":
                    row.transcript, row.stage = result, "structure"
                    # The successful paid checkpoint makes audio redownload and
                    # subsequent STT unnecessary; retain only the Drive link.
                    row.downloaded_audio = None
                elif stage == "structure":
                    row.structure, row.stage = result.model_dump(mode="json"), "proposals"
                else:
                    previous = (await session.scalars(select(CallProposal).where(CallProposal.recording_id == row.id))).all()
                    adopted = (await session.scalars(select(CallAdoption).where(CallAdoption.connection_id == row.connection_id, CallAdoption.file_id == row.file_id))).all()
                    adopted_keys = {item.action_key for item in adopted}
                    # Rebuilding after manual source corrections preserves IDs
                    # and adopted material; only still-pending payloads refresh.
                    by_key = {item.action_key: item for item in previous}
                    for values in result:
                        proposal = by_key.get(values["action_key"])
                        if proposal is None:
                            proposal = CallProposal(recording_id=row.id, **values)
                        elif proposal.action_key not in adopted_keys:
                            proposal.payload = values["payload"]
                            proposal.needs_clarification = values["needs_clarification"]
                        session.add(proposal)
                    row.state = "ready_for_review" if result else "manual_review"
                row.version += 1
                row.updated_at = datetime.now(timezone.utc)
                session.add(row)
                await session.commit()
            if stage == "transcribe" and snapshot["transcription_provider"] == "google_batch" and not injected_transcriber:
                await GoogleCallBatchTranscriptionProvider.delete_audio(source_id=source_id)
            if stage == "proposals":
                return

    @staticmethod
    async def transcribe(**kwargs):
        key = settings.CALL_RECORDINGS_TRANSCRIPTION_API_KEY.strip()
        if not key:
            raise CallDriveError("call_transcription_not_configured", "Распознавание звонков не настроено", status_code=503)
        return await BotVoiceTranscriptionProvider.transcribe(**kwargs, configuration=(settings.CALL_RECORDINGS_TRANSCRIPTION_API_URL, key, settings.CALL_RECORDINGS_TRANSCRIPTION_MODEL, 60.0))
