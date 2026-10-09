"""Bounded outbox consumer sharing the established renewable lease primitive."""

import asyncio
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlmodel import select

from core.config import settings
from core.database import async_session_maker
from models import IntegrationOutboxEvent
from models.call_recording import CallDriveConnection, CallRecording
from services.call_recording_pipeline import CallLeaseLost, CallRecordingPipeline, CallTranscriptionPending, fenced_recording
from services.call_recording_service import CALL_EVENT_TYPE
from services.repair_diagnostic_ai_job_service import RepairDiagnosticAiJobService


@dataclass(frozen=True)
class CallJobClaim:
    event_id: str
    lease_token: str
    worker_id: str
    recording_id: int
    connection_id: int
    attempts: int
    max_attempts: int


class CallRecordingJobService(RepairDiagnosticAiJobService):
    # Reuse renewal/heartbeat/backoff, with an independently filtered queue and
    # call checkpoints. Unknown event types are never claimed by this consumer.
    LEASE_SECONDS = 300

    @classmethod
    async def claim(cls, session, *, worker_id, now):
        eligible = or_(and_(IntegrationOutboxEvent.status == "pending", IntegrationOutboxEvent.available_at <= now), and_(IntegrationOutboxEvent.status == "processing", IntegrationOutboxEvent.lease_expires_at <= now))
        event = await session.scalar(select(IntegrationOutboxEvent).where(IntegrationOutboxEvent.event_type == CALL_EVENT_TYPE, eligible).order_by(IntegrationOutboxEvent.available_at, IntegrationOutboxEvent.event_id).limit(1).with_for_update(skip_locked=True))
        if event is None:
            return None
        if event.attempts >= event.max_attempts:
            row = await session.get(CallRecording, event.payload["recording_id"], with_for_update=True)
            if row:
                row.state, row.last_error_code = "manual_review", "call_job_exhausted"
                row.version += 1
                session.add(row)
            event.status = "dead"
            event.worker_id = event.lease_token = event.lease_expires_at = None
            session.add(event)
            return None
        event.status, event.worker_id = "processing", str(worker_id)[:128]
        event.lease_token = secrets.token_hex(16)
        event.lease_expires_at = now + timedelta(seconds=cls.LEASE_SECONDS)
        event.attempts += 1
        session.add(event)
        await session.flush()
        return CallJobClaim(event.event_id, event.lease_token, event.worker_id, int(event.payload["recording_id"]), int(event.payload["connection_id"]), event.attempts, event.max_attempts)

    @classmethod
    async def finish(cls, session, claim, error):
        try:
            row = await fenced_recording(session, claim)
        except CallLeaseLost:
            return "lease_lost"
        event = await session.get(IntegrationOutboxEvent, claim.event_id)
        event.worker_id = event.lease_token = event.lease_expires_at = None
        if error is None:
            event.status, event.published_at = "published", datetime.now(timezone.utc)
            event.last_error_code = event.last_error_message = None
        elif isinstance(error, CallTranscriptionPending):
            row.state, row.last_error_code = "waiting_transcription", None
            row.version += 1
            row.updated_at = datetime.now(timezone.utc)
            event.status = "pending"
            # A status check is neither a failure nor a paid speech submission.
            event.attempts = max(0, event.attempts - 1)
            event.available_at = datetime.now(timezone.utc) + timedelta(minutes=5)
            event.last_error_code = event.last_error_message = None
            session.add(row)
        else:
            code = str(getattr(error, "code", type(error).__name__))[:100]
            row.last_error_code = code
            row.version += 1
            if isinstance(error, PermissionError):
                row.state, event.status = "manual_review", "dead"
            elif code in {"google_drive_access_denied", "call_drive_not_connected", "credentials_unreadable", "credential_encryption_unavailable", "call_connection_changed", "call_transcription_not_configured", "call_google_not_configured", "call_google_access_denied", "not_configured", "authentication_rejected"}:
                row.state, event.status = "reconnect_required", "dead"
            elif (row.stage_attempts.get(row.stage, 0) >= 3 and not (row.stage == "transcribe" and row.transcription_operation)) or claim.attempts >= claim.max_attempts or code in {"call_source_changed", "call_upload_changed", "call_file_outside_folder", "call_stage_exhausted", "call_google_wait_expired", "call_google_invalid_audio", "call_google_operation_failed", "BotVoiceAudioValidationError", "BotVoiceTranscriptionInvalidAudioError"}:
                row.state, event.status = "manual_review", "dead"
            else:
                row.state, event.status = "failed", "pending"
                event.available_at = datetime.now(timezone.utc) + cls._retry_delay(claim.attempts)
            event.last_error_code = code
            # Provider messages can contain transcript/key material. Persist a
            # stable code and a fixed safe message, never the exception body.
            event.last_error_message = "Call recording stage failed"
            session.add(row)
        session.add(event)
        await session.flush()
        return event.status

    @classmethod
    async def process_batch(cls, *, worker_id, limit=3, session_factory=None, runner=None):
        if not settings.CALL_RECORDINGS_ENABLED:
            return 0
        factory = session_factory or async_session_maker
        selected_runner = runner or CallRecordingPipeline.run
        processed = 0
        for _ in range(max(1, min(int(limit), 3))):
            async with factory() as session:
                async with session.begin():
                    claim = await cls.claim(session, worker_id=worker_id, now=datetime.now(timezone.utc))
            if claim is None:
                break
            stop = asyncio.Event()
            heartbeat = asyncio.create_task(cls._heartbeat_loop(claim=claim, session_factory=factory, stop=stop))
            run = asyncio.create_task(selected_runner(claim=claim, session_factory=factory))
            error = None
            try:
                done, _ = await asyncio.wait({run, heartbeat}, return_when=asyncio.FIRST_COMPLETED)
                if heartbeat in done and not heartbeat.result():
                    run.cancel()
                    error = CallLeaseLost()
                else:
                    try:
                        await run
                    except Exception as exc:
                        error = exc
            except asyncio.CancelledError:
                run.cancel()
                heartbeat.cancel()
                await asyncio.gather(run, heartbeat, return_exceptions=True)
                raise
            finally:
                stop.set()
                await asyncio.gather(run, heartbeat, return_exceptions=True)
            async with factory() as session:
                async with session.begin():
                    await cls.finish(session, claim, error)
            processed += 1
        return processed

    @classmethod
    async def poll_auto_connections(cls, *, session_factory=None):
        if not settings.CALL_RECORDINGS_ENABLED:
            return 0
        from core.command_actor import CommandActor
        from models import StaffUser
        from models.tenancy import TenantScope
        from services.call_recording_service import CallRecordingService
        factory = session_factory or async_session_maker
        async with factory() as session:
            rows = (await session.scalars(select(CallDriveConnection).where(CallDriveConnection.auto_poll_enabled.is_(True), CallDriveConnection.encrypted_credentials.is_not(None), CallDriveConnection.folder_id.is_not(None), or_(CallDriveConnection.last_polled_at.is_(None), CallDriveConnection.last_polled_at < datetime.now(timezone.utc) - timedelta(seconds=60))).limit(3))).all()
            snapshots = [row.model_dump() for row in rows]
        for row in snapshots:
            async with factory() as session:
                user = await session.get(StaffUser, row["staff_user_id"])
                actor = CommandActor(row["staff_user_id"], user.username or str(user.id), TenantScope(row["tenant_id"], row["storefront_id"]), "drive_call")
                try:
                    await CallRecordingService.poll(session, actor)
                except Exception:
                    await session.rollback()
                    # One revoked source must not block other owners' jobs.
        return len(snapshots)
