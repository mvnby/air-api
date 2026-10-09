import asyncio
import hashlib
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import event, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from core.command_actor import CommandActor
from core.config import settings
from models import IntegrationOutboxEvent, Lead, Order, OrderWorkStage, StaffUser, TenantMembership, Tenant, Storefront
from models.call_recording import CallAdoption, CallDriveConnection, CallProposal, CallRecording
from models.command_audit import CommandAuditEvent
from models.personal_task import PersonalTask
from models.tenancy import TenantScope
from schemas_call_recordings import CallAdoptPayload, CallFolderPayload, CallRetryPayload, CallRecordingMetadataPayload
from schemas_incoming import IncomingFields
from schemas_personal_tasks import PersonalTaskCreatePayload
from services.bot_voice_audio_normalizer import BotNormalizedVoiceAudio
from services.call_drive_connection_service import CallDriveConnectionService, CallDriveCredentialCipher
from services.call_drive_provider import CallDriveError
from services.call_recording_job_service import CallRecordingJobService
from services.call_recording_pipeline import CallLeaseLost, CallRecordingPipeline, fenced_recording
from services.call_recording_service import CallRecordingService
from services.call_recording_structure import ExtractedCall
from services.incoming_command_service import IncomingCommandService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict


CONTENT = b"bounded-fake-audio"
FILE_ID = "safe-file-00000001"
FOLDER_ID = "chosen-folder-00000001"
TRANSCRIPT = "Нужно обслуживание в Уручье завтра утром. Телефон +375291234567. Дослать фото свидетельства. Перезвонить завтра в 9:00."


class Provider:
    def __init__(self):
        self.version = "1"
        self.downloads = 0
        self.change_during_download = False
        self.denied = False

    async def access_token(self, credentials):
        if self.denied:
            raise CallDriveError("google_drive_access_denied", "Отозвано")
        return "test-token"

    def adapter(self, token):
        return self

    async def account_label(self):
        return "test-owner@example.invalid"

    async def folder(self, folder):
        return {"id": folder, "name": "Тестовая папка"}

    async def metadata(self, file):
        return {"id": file, "name": "Вызов Неподтверждённое имя_261008_185601.m4a", "mimeType": "video/3gpp", "size": str(len(CONTENT)), "md5Checksum": hashlib.md5(CONTENT).hexdigest(), "version": self.version, "headRevisionId": self.version, "modifiedTime": "2026-10-08T16:10:00Z", "parents": [FOLDER_ID]}

    async def list_recordings(self, folder, **kwargs):
        return [await self.metadata(FILE_ID)], None

    async def download_audio(self, file):
        self.downloads += 1
        if self.change_during_download:
            self.version = "2"
        return CONTENT


@pytest.fixture
async def context(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "CALL_RECORDINGS_ENABLED", True)
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    provider = Provider()
    async with factory() as session:
        user = StaffUser(display_name="Автор звонков", username="call-owner", roles=["manager"], primary_role="manager")
        session.add(user)
        await session.flush()
        session.add(TenantMembership(staff_user_id=user.id, tenant_id=1, role="manager", status="active"))
        await session.commit()
        actor = CommandActor(user.id, user.username, TenantScope(1, 1, is_system=True), "manager")
        await CallDriveConnectionService.authorize(session, actor, {"token": "secret-test-token", "scopes": ["https://www.googleapis.com/auth/drive.readonly"]}, provider=provider)
        await CallDriveConnectionService.configure(session, actor, CallFolderPayload(folder_id=FOLDER_ID), provider=provider)
    return factory, actor, provider


async def queue(context):
    factory, actor, provider = context
    now = datetime.now(timezone.utc)
    async with factory() as session:
        first = await CallRecordingService.poll(session, actor, file_id=FILE_ID, provider=provider, now=now)
        assert first.queued == 0
        second = await CallRecordingService.poll(session, actor, file_id=FILE_ID, provider=provider, now=now + timedelta(seconds=61))
        assert second.queued == 1
        return (await session.scalar(select(CallRecording).order_by(CallRecording.id.desc()))).id


def runner(context, *, structure_fail_once=False):
    factory, actor, provider = context
    calls = {"normalize": 0, "transcribe": 0, "structure": 0}

    async def normalize(**kwargs):
        calls["normalize"] += 1
        assert kwargs["mime_type"] == "video/3gpp"
        return BotNormalizedVoiceAudio(CONTENT, "call.wav", "audio/wav", 75)

    async def transcribe(**kwargs):
        calls["transcribe"] += 1
        return TRANSCRIPT

    async def extract(**kwargs):
        calls["structure"] += 1
        if structure_fail_once and calls["structure"] == 1:
            raise TimeoutError("fake provider failure must not expose transcript")
        return ExtractedCall(summary="Три независимых действия", actions=[
            {"kind": "incoming", "text": "Нужно обслуживание", "evidence": "Нужно обслуживание в Уручье завтра утром", "phone": "+375291234567", "region_text": "Уручье", "requested_time_text": "завтра утром", "service_type": "maintenance", "clarification_requested": True},
            {"kind": "task", "text": "Дослать фото свидетельства", "evidence": "Дослать фото свидетельства"},
            {"kind": "callback", "text": "Перезвонить", "evidence": "Перезвонить завтра в 9:00", "requested_time_text": "завтра в 9:00"},
        ])

    async def run(**kwargs):
        return await CallRecordingPipeline.run(**kwargs, provider=provider, normalizer=normalize, transcriber=transcribe, extractor=extract)
    return run, calls


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_list_does_not_read_saved_audio_or_paid_checkpoints(context, db_engine):
    factory, actor, provider = context
    recording_id = await queue(context)
    checkpoint = b"saved-normalized-audio" * 4096
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        row.downloaded_audio = checkpoint
        row.audio_duration_seconds = 75
        row.state, row.stage = "failed", "transcribe"
        row.stage_attempts = {"download": 1, "transcribe": 1}
        source_url = row.source_url
        session.add(row)
        await session.commit()

    statements = []
    def capture(connection, cursor, statement, parameters, execution_context, executemany):
        statements.append(statement.lower())
    event.listen(db_engine.sync_engine, "before_cursor_execute", capture)
    try:
        # Use a fresh consumer session so the checkpoint cannot come from the
        # identity map. Any accidental lazy read is included in captured SQL.
        async with factory() as session:
            result = await CallRecordingService.list(session, actor, limit=100)
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", capture)
    assert result.total == 1 and len(result.items) == 1
    item = result.items[0]
    assert item.id == recording_id and item.source_url == source_url
    assert item.state == "failed" and item.stage == "transcribe"
    assert item.audio_duration_seconds == 75 and item.stage_attempts["download"] == 1
    assert item.transcript is None and item.structure is None and item.proposals == []
    reads = [statement for statement in statements if "from call_recording" in statement]
    assert any("call_recording.id" in statement for statement in reads)
    for column in ("downloaded_audio", "transcript", "structure"):
        assert not any(re.search(rf"\bcall_recording\.{column}\b", statement) for statement in reads)
    async with factory() as session:
        assert (await session.get(CallRecording, recording_id)).downloaded_audio == checkpoint


@pytest.mark.asyncio
async def test_stable_drive_file_end_to_end_explicit_multiple_adoptions_and_changed_version(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context)
    assert await CallRecordingJobService.process_batch(worker_id="one", session_factory=factory, runner=run) == 1
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.state == "ready_for_review" and row.transcript == TRANSCRIPT
        assert row.call_occurred_at.isoformat() == "2026-10-08T15:56:01+00:00"
        assert len(row.proposals) == 3
        assert await count(session, Lead) == await count(session, PersonalTask) == 0
        incoming = row.proposals[0]
        assert incoming.requested_date.isoformat() == "2026-10-09" and incoming.date_precision == "date"
        assert incoming.payload["requested_at"] is None
        payload = CallAdoptPayload(expected_version=row.version, incoming=IncomingFields(**incoming.payload))
        created = await CallRecordingService.adopt(session, actor, recording_id, incoming.id, payload)
        replay = await CallRecordingService.adopt(session, actor, recording_id, incoming.id, payload)
        assert replay.resource_id == created.resource_id and replay.replayed
        lead = await session.get(Lead, created.resource_id)
        assert lead.phone == "+375291234567"
        assert lead.intake_meta["channel"] == "drive_call"
        assert lead.intake_meta["requested_at"].startswith("2026-10-09")
        assert lead.intake_meta["source_occurred_at"].startswith("2026-10-08")
        assert lead.intake_meta["clarification_task_id"]
        assert lead.intake_meta["source_url"] == row.source_url
        saved = await IncomingCommandService.get(session, actor=actor, lead_id=lead.id)
        assert saved.source_url == row.source_url
        assert saved.date_precision == "date" and saved.requested_time_text == "завтра утром"
        assert saved.requested_at.astimezone(ZoneInfo("Europe/Minsk")).date().isoformat() == "2026-10-09"
        assert saved.field_sources["requested_at"] == "text"
        assert saved.field_sources["requested_time_text"] == "provided"
        task_proposal = row.proposals[1]
        await CallRecordingService.adopt(session, actor, recording_id, task_proposal.id, CallAdoptPayload(expected_version=row.version, task=PersonalTaskCreatePayload(**task_proposal.payload)))
        assert await count(session, PersonalTask) == 2
        assert await count(session, Order) == await count(session, OrderWorkStage) == 0
        assert await count(session, CommandAuditEvent) >= 3
        assert await count(session, CallAdoption) == 2
        changed = payload.model_copy(update={"incoming": IncomingFields(request_text="Другая заявка")})
        with pytest.raises(PublicWriteIdempotencyConflict):
            await CallRecordingService.adopt(session, actor, recording_id, incoming.id, changed)
    provider.version = "2"
    second_id = await queue(context)
    assert second_id != recording_id
    await CallRecordingJobService.process_batch(worker_id="two", session_factory=factory, runner=run)
    assert calls == {"normalize": 1, "transcribe": 1, "structure": 1}
    async with factory() as session:
        changed_row = await CallRecordingService.get(session, actor, second_id)
        assert changed_row.proposals[0].accepted_resource_id == created.resource_id
        assert changed_row.proposals[0].date_precision == "date"
        assert changed_row.proposals[0].requested_date.isoformat() == "2026-10-09"
        replay = await CallRecordingService.adopt(session, actor, second_id, changed_row.proposals[0].id, CallAdoptPayload(expected_version=changed_row.version, incoming=IncomingFields(**changed_row.proposals[0].payload)))
        assert replay.replayed and await count(session, Lead) == 1
        assert (await CallRecordingService.get(session, actor, recording_id)).transcript == TRANSCRIPT
        with pytest.raises(PublicWriteIdempotencyConflict):
            await CallRecordingService.adopt(session, actor, second_id, changed_row.proposals[0].id, CallAdoptPayload(expected_version=changed_row.version, incoming=IncomingFields(request_text="Попытка исправить уже сохранённое через новую версию")))


@pytest.mark.asyncio
async def test_structuring_failure_resumes_without_paid_transcription_or_download(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context, structure_fail_once=True)
    await CallRecordingJobService.process_batch(worker_id="first", session_factory=factory, runner=run)
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.state == "failed" and row.stage == "structure" and row.transcript == TRANSCRIPT
        await CallRecordingService.retry(session, actor, recording_id, CallRetryPayload(expected_version=row.version))
    await CallRecordingJobService.process_batch(worker_id="restart", session_factory=factory, runner=run)
    assert calls == {"normalize": 1, "transcribe": 1, "structure": 2}
    assert provider.downloads == 1


@pytest.mark.asyncio
async def test_download_reread_changed_revision_stops_before_paid_calls(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    provider.change_during_download = True
    run, calls = runner(context)
    await CallRecordingJobService.process_batch(worker_id="one", session_factory=factory, runner=run)
    assert calls == {"normalize": 0, "transcribe": 0, "structure": 0}
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.state == "manual_review" and row.last_error_code == "call_source_changed"
        assert row.transcript is None


@pytest.mark.asyncio
async def test_revoked_drive_retry_preserves_stage_budget(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context)
    provider.denied = True
    await CallRecordingJobService.process_batch(worker_id="one", session_factory=factory, runner=run)
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.state == "reconnect_required"
        provider.denied = False
        await CallDriveConnectionService.authorize(session, actor, {"token": "new-test-token", "scopes": ["https://www.googleapis.com/auth/drive.readonly"]}, provider=provider)
        await CallRecordingService.retry(session, actor, recording_id, CallRetryPayload(expected_version=row.version))
    await CallRecordingJobService.process_batch(worker_id="two", session_factory=factory, runner=run)
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.state == "ready_for_review" and row.stage_attempts["download"] == 2


@pytest.mark.asyncio
async def test_private_scope_demotion_and_cipher_are_fail_closed(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    async with factory() as session:
        other = StaffUser(display_name="Другой", username="other-call-owner", roles=["manager"], primary_role="manager")
        session.add(other)
        await session.flush()
        session.add(TenantMembership(staff_user_id=other.id, tenant_id=1, role="manager", status="active"))
        await session.commit()
        other_actor = replace(actor, staff_user_id=other.id, username=other.username)
        with pytest.raises(LookupError):
            await CallRecordingService.get(session, other_actor, recording_id)
        tenant = Tenant(slug="call-other-tenant", display_name="Другая компания")
        session.add(tenant)
        await session.flush()
        storefront = Storefront(tenant_id=tenant.id, slug="call-other-storefront", display_name="Другая витрина", status="active")
        session.add(storefront)
        await session.flush()
        session.add(TenantMembership(staff_user_id=actor.staff_user_id, tenant_id=tenant.id, role="manager", status="active"))
        await session.commit()
        with pytest.raises(LookupError):
            await CallRecordingService.get(session, replace(actor, tenant_scope=TenantScope(tenant.id, storefront.id)), recording_id)
        with pytest.raises(PermissionError):
            await CallRecordingService.get(session, replace(actor, tenant_scope=TenantScope(999, 1)), recording_id)
        connection = await CallDriveConnectionService.get(session, actor)
        assert "secret-test-token" not in connection.encrypted_credentials
        with pytest.raises(ValueError):
            CallDriveCredentialCipher.decrypt(connection.encrypted_credentials, tenant_id=1, provider=f"call-drive:{other.id}:1")
        membership = await session.scalar(select(TenantMembership).where(TenantMembership.staff_user_id == actor.staff_user_id, TenantMembership.tenant_id == 1))
        membership.role = "installer"
        session.add(membership)
        await session.commit()
        with pytest.raises(PermissionError):
            await CallRecordingService.get(session, actor, recording_id)
    run, calls = runner(context)
    await CallRecordingJobService.process_batch(worker_id="demoted", session_factory=factory, runner=run)
    assert calls == {"normalize": 0, "transcribe": 0, "structure": 0}


@pytest.mark.asyncio
async def test_concurrent_observation_claim_and_expired_lease_cannot_save(context):
    factory, actor, provider = context
    now = datetime.now(timezone.utc)
    async def poll(at):
        async with factory() as session:
            return await CallRecordingService.poll(session, actor, provider=provider, now=at)
    await poll(now)
    results = await asyncio.gather(poll(now + timedelta(seconds=61)), poll(now + timedelta(seconds=61)))
    assert sum(result.queued for result in results) == 1
    async def claim(worker):
        async with factory() as session:
            async with session.begin():
                return await CallRecordingJobService.claim(session, worker_id=worker, now=datetime.now(timezone.utc))
    claims = await asyncio.gather(claim("first"), claim("second"))
    claim_one = next(item for item in claims if item)
    assert sum(item is not None for item in claims) == 1
    async with factory() as session:
        event = await session.get(IntegrationOutboxEvent, claim_one.event_id)
        event.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(event)
        await session.commit()
        with pytest.raises(CallLeaseLost):
            await fenced_recording(session, claim_one)
    claim_two = await claim("recovered")
    assert claim_two.lease_token != claim_one.lease_token
    async with factory() as session:
        assert await CallRecordingJobService.finish(session, claim_one, None) == "lease_lost"
        assert (await session.get(IntegrationOutboxEvent, claim_two.event_id)).lease_token == claim_two.lease_token


@pytest.mark.asyncio
async def test_default_off_and_stage_cap_are_not_reset_by_manual_retry(context, monkeypatch):
    factory, actor, provider = context
    monkeypatch.setattr(settings, "CALL_RECORDINGS_ENABLED", False)
    async with factory() as session:
        with pytest.raises(CallDriveError, match="выключена"):
            await CallRecordingService.poll(session, actor, provider=provider)
    assert await CallRecordingJobService.process_batch(worker_id="disabled", session_factory=factory) == 0
    monkeypatch.setattr(settings, "CALL_RECORDINGS_ENABLED", True)
    recording_id = await queue(context)
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        row.state, row.stage, row.stage_attempts = "manual_review", "transcribe", {"download": 1, "transcribe": 3}
        session.add(row)
        await session.commit()
        with pytest.raises(CallDriveError, match="исчерпан"):
            await CallRecordingService.retry(session, actor, recording_id, CallRetryPayload(expected_version=row.version))


@pytest.mark.asyncio
@pytest.mark.parametrize("manual_time", [None, "2026-10-11T14:30:00+03:00"])
async def test_saved_incoming_date_precision_and_accepted_day_survive_source_clock_correction(context, manual_time):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context)
    await CallRecordingJobService.process_batch(worker_id="date-review", session_factory=factory, runner=run)
    expected_day = "2026-10-11" if manual_time else "2026-10-09"
    precision = "datetime" if manual_time else "date"
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        proposal = row.proposals[0]
        fields = IncomingFields(**{**proposal.payload, "requested_at": manual_time})
        payload = CallAdoptPayload(expected_version=row.version, incoming=fields)
        adoption = await CallRecordingService.adopt(session, actor, row.id, proposal.id, payload)
        saved = await IncomingCommandService.get(session, actor=actor, lead_id=adoption.resource_id)
        assert saved.date_precision == precision and saved.requested_time_text == "завтра утром"
        assert saved.requested_at.astimezone(ZoneInfo("Europe/Minsk")).date().isoformat() == expected_day
        if manual_time:
            assert saved.requested_at == datetime.fromisoformat(manual_time)
        receipt = await session.scalar(select(CallAdoption).where(CallAdoption.proposal_id == proposal.id))
        assert receipt.payload == payload.model_dump(mode="json", exclude={"expected_version"})
        corrected = await CallRecordingService.metadata(session, actor, row.id, CallRecordingMetadataPayload(expected_version=row.version, call_occurred_at=row.call_occurred_at + timedelta(days=7)))
        await CallRecordingService.retry(session, actor, row.id, CallRetryPayload(expected_version=corrected.version))
    await CallRecordingJobService.process_batch(worker_id="date-rebuild", session_factory=factory, runner=run)
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        accepted = row.proposals[0]
        assert accepted.date_precision == precision and accepted.requested_date.isoformat() == expected_day
        assert accepted.payload == fields.model_dump(mode="json")
        assert await count(session, Lead) == 1
    assert calls == {"normalize": 1, "transcribe": 1, "structure": 1}


@pytest.mark.asyncio
async def test_adopted_payload_and_actual_callback_deadline_survive_manual_clock_correction(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context)
    await CallRecordingJobService.process_batch(worker_id="first", session_factory=factory, runner=run)
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        callback = row.proposals[2]
        stored = await session.get(CallProposal, callback.id)
        original_payload = dict(stored.payload)
        receipt = await CallRecordingService.adopt(session, actor, recording_id, callback.id, CallAdoptPayload(expected_version=row.version, task=PersonalTaskCreatePayload(**callback.payload)))
        actual = await session.get(PersonalTask, receipt.resource_id)
        original_due = actual.due_at
        corrected = await CallRecordingService.metadata(session, actor, recording_id, CallRecordingMetadataPayload(expected_version=row.version, call_occurred_at=row.call_occurred_at + timedelta(days=7), phone="+375291111111"))
        await CallRecordingService.retry(session, actor, recording_id, CallRetryPayload(expected_version=corrected.version))
    await CallRecordingJobService.process_batch(worker_id="rebuild", session_factory=factory, runner=run)
    async with factory() as session:
        stored = await session.get(CallProposal, callback.id)
        assert stored.payload == original_payload
        assert (await session.get(PersonalTask, receipt.resource_id)).due_at == original_due
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.proposals[2].accepted_resource_id == receipt.resource_id
        assert row.proposals[2].payload["due_at"] == callback.payload["due_at"]
        assert await count(session, PersonalTask) == 1
        assert row.proposals[0].payload["phone"] == "+375291111111"
    assert calls == {"normalize": 1, "transcribe": 1, "structure": 1}


@pytest.mark.asyncio
async def test_concurrent_adoption_atomic_failure_and_durable_receipt(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context)
    await CallRecordingJobService.process_batch(worker_id="first", session_factory=factory, runner=run)
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        proposal = row.proposals[1]
        bad_payload = CallAdoptPayload(expected_version=row.version, task=PersonalTaskCreatePayload(text="Дослать фото", lead_id=999999))
        with pytest.raises(ValueError):
            await CallRecordingService.adopt(session, actor, recording_id, proposal.id, bad_payload)
        assert await count(session, PersonalTask) == await count(session, CallAdoption) == 0
    payload = CallAdoptPayload(expected_version=row.version, task=PersonalTaskCreatePayload(**proposal.payload))
    async def adopt():
        async with factory() as session:
            return await CallRecordingService.adopt(session, actor, recording_id, proposal.id, payload)
    results = await asyncio.gather(adopt(), adopt())
    assert results[0].resource_id == results[1].resource_id
    assert sorted(result.replayed for result in results) == [False, True]
    async with factory() as session:
        from models import PublicWriteIdempotency
        from sqlalchemy import delete
        await session.execute(delete(PublicWriteIdempotency))
        await session.commit()
        replay = await CallRecordingService.adopt(session, actor, recording_id, proposal.id, payload)
        assert replay.replayed and await count(session, PersonalTask) == 1


@pytest.mark.asyncio
async def test_transcription_retry_reuses_download_checkpoint_and_has_independent_stage_count(context):
    factory, actor, provider = context
    recording_id = await queue(context)
    run, calls = runner(context)
    original = CallRecordingPipeline.run
    attempt = 0
    async def failed_once(**kwargs):
        nonlocal attempt
        async def transcribe(**values):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise TimeoutError("temporary speech outage")
            return TRANSCRIPT
        async def normalize(**values):
            return BotNormalizedVoiceAudio(CONTENT, "call.wav", "audio/wav", 75)
        async def extract(**values):
            return ExtractedCall(summary="Материал для ручного разбора", actions=[])
        await original(**kwargs, provider=provider, normalizer=normalize, transcriber=transcribe, extractor=extract)
    await CallRecordingJobService.process_batch(worker_id="one", session_factory=factory, runner=failed_once)
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.state == "failed" and row.stage == "transcribe"
        await CallRecordingService.retry(session, actor, recording_id, CallRetryPayload(expected_version=row.version))
    await CallRecordingJobService.process_batch(worker_id="two", session_factory=factory, runner=failed_once)
    assert provider.downloads == 1 and attempt == 2
    async with factory() as session:
        row = await CallRecordingService.get(session, actor, recording_id)
        assert row.stage_attempts == {"download": 1, "transcribe": 2, "structure": 1}
        assert row.state == "manual_review" and row.transcript == TRANSCRIPT


@pytest.mark.asyncio
async def test_call_credential_is_in_health_and_rotation_registry(context):
    factory, actor, provider = context
    from services.integration_credential_health import integration_credential_health
    from services.integration_credential_rotation_service import IntegrationCredentialRotationService
    async with factory() as session:
        health = await integration_credential_health(session)
        assert health["checked"] == 1 and health["unreadable"] == 0
        plan = await IntegrationCredentialRotationService.plan(session)
        assert plan["rows"][0]["domain"] == "call_drive"
        assert "secret-test-token" not in str(plan)
        connection = await CallDriveConnectionService.get(session, actor, for_update=True)
        connection.encrypted_credentials = "unreadable"
        session.add(connection)
        await session.commit()
        assert (await integration_credential_health(session))["unreadable"] == 1


async def google_runner(context, monkeypatch, *, poll_results=None, structure_errors=0):
    from services.call_google_batch_transcription import GoogleCallBatchTranscriptionProvider as google
    factory, actor, provider = context
    calls = {"submit": 0, "poll": 0, "delete": 0, "structure": 0}
    results = list(poll_results or [])
    monkeypatch.setattr(google, "is_configured", lambda: True)
    async with factory() as session:
        status = await CallDriveConnectionService.configure(session, actor, CallFolderPayload(folder_id=FOLDER_ID, transcription_provider="google_batch"), provider=provider)
        assert status.transcription_provider == "google_batch" and status.transcription_configured
        assert not status.auto_poll_enabled

    async def submit(**kwargs):
        calls["submit"] += 1
        assert kwargs["content"] == CONTENT and len(kwargs["source_id"]) == 64
        return "projects/airconditionersbot/locations/eu/operations/test-operation"

    async def poll(**kwargs):
        calls["poll"] += 1
        assert kwargs["operation_name"].endswith("/test-operation")
        value = results.pop(0) if results else None
        if isinstance(value, Exception):
            raise value
        return value

    async def delete(**kwargs):
        calls["delete"] += 1
        async with factory() as session:
            row = await session.scalar(select(CallRecording).where(CallRecording.transcription_operation.is_not(None)))
            assert row.transcript == TRANSCRIPT and row.downloaded_audio is None
        return True

    async def normalize(**kwargs):
        return BotNormalizedVoiceAudio(CONTENT, "call.wav", "audio/wav", 75)

    async def extract(**kwargs):
        calls["structure"] += 1
        if calls["structure"] <= structure_errors:
            raise TimeoutError("private provider message must not be stored")
        return ExtractedCall(summary="Поручение", actions=[{"kind": "task", "text": "Дослать фото свидетельства", "evidence": "Дослать фото свидетельства"}])

    monkeypatch.setattr(google, "submit", submit)
    monkeypatch.setattr(google, "poll", poll)
    monkeypatch.setattr(google, "delete_audio", delete)

    async def run(**kwargs):
        await CallRecordingPipeline.run(**kwargs, provider=provider, normalizer=normalize, extractor=extract)
    return run, calls


async def make_google_event_available(factory, recording_id):
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        event = await session.get(IntegrationOutboxEvent, row.job_event_id)
        event.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.add(event)
        await session.commit()


@pytest.mark.asyncio
async def test_google_wait_is_durable_and_does_not_exhaust_or_resubmit(context, monkeypatch):
    factory, actor, provider = context
    run, calls = await google_runner(context, monkeypatch, poll_results=[None] * 10 + [TRANSCRIPT])
    recording_id = await queue(context)
    assert await CallRecordingJobService.process_batch(worker_id="google-first", limit=1, session_factory=factory, runner=run) == 1
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        assert row.state == "waiting_transcription" and row.transcription_operation
        assert row.stage_attempts == {"download": 1, "transcribe": 1}
        operation = row.transcription_operation
        # Changing the folder preference cannot change an already submitted job.
        await CallDriveConnectionService.configure(session, actor, CallFolderPayload(folder_id=FOLDER_ID, transcription_provider="groq"), provider=provider)
    for index in range(10):
        await make_google_event_available(factory, recording_id)
        await CallRecordingJobService.process_batch(worker_id=f"google-restart-{index}", limit=1, session_factory=factory, runner=run)
        async with factory() as session:
            row = await session.get(CallRecording, recording_id)
            event = await session.get(IntegrationOutboxEvent, row.job_event_id)
            assert row.state == "waiting_transcription" and row.last_error_code is None
            assert row.transcription_operation == operation and row.transcription_provider == "google_batch"
            assert row.stage_attempts["transcribe"] == 1 and event.attempts == 0
    await make_google_event_available(factory, recording_id)
    await CallRecordingJobService.process_batch(worker_id="google-ready", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        detail = await CallRecordingService.get(session, actor, recording_id)
        assert detail.state == "ready_for_review" and detail.transcript == TRANSCRIPT
        assert detail.transcription_provider == "google_batch" and detail.transcription_model == "chirp_3"
        assert len(detail.proposals) == 1 and detail.stage_attempts["transcribe"] == 1
        assert await count(session, Lead) == await count(session, PersonalTask) == 0
    assert calls == {"submit": 1, "poll": 11, "delete": 1, "structure": 1} and provider.downloads == 1


@pytest.mark.asyncio
async def test_google_wait_deadline_stops_without_new_paid_submission(context, monkeypatch):
    factory, actor, provider = context
    run, calls = await google_runner(context, monkeypatch)
    recording_id = await queue(context)
    await CallRecordingJobService.process_batch(worker_id="google-first", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        row.transcription_submitted_at = datetime.now(timezone.utc) - timedelta(hours=27)
        session.add(row)
        await session.commit()
    await make_google_event_available(factory, recording_id)
    await CallRecordingJobService.process_batch(worker_id="google-expired", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        event = await session.get(IntegrationOutboxEvent, row.job_event_id)
        assert row.state == "manual_review" and row.last_error_code == "call_google_wait_expired"
        assert event.status == "dead" and row.stage_attempts["transcribe"] == 1
    assert calls["submit"] == 1 and calls["poll"] == calls["structure"] == 0


@pytest.mark.asyncio
async def test_google_poll_failure_recovers_the_same_operation(context, monkeypatch):
    factory, actor, provider = context
    run, calls = await google_runner(context, monkeypatch, poll_results=[CallDriveError("call_google_provider_error", "redacted"), None, TRANSCRIPT])
    recording_id = await queue(context)
    await CallRecordingJobService.process_batch(worker_id="google-first", limit=1, session_factory=factory, runner=run)
    for index in range(3):
        await make_google_event_available(factory, recording_id)
        await CallRecordingJobService.process_batch(worker_id=f"google-recovery-{index}", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        assert row.state == "ready_for_review" and row.stage_attempts["transcribe"] == 1
    assert calls == {"submit": 1, "poll": 3, "delete": 1, "structure": 1}


@pytest.mark.asyncio
async def test_google_saved_operation_does_not_remove_structure_retry_limit(context, monkeypatch):
    factory, actor, provider = context
    run, calls = await google_runner(context, monkeypatch, poll_results=[TRANSCRIPT], structure_errors=3)
    recording_id = await queue(context)
    await CallRecordingJobService.process_batch(worker_id="google-first", limit=1, session_factory=factory, runner=run)
    for index in range(3):
        await make_google_event_available(factory, recording_id)
        await CallRecordingJobService.process_batch(worker_id=f"google-structure-{index}", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        event = await session.get(IntegrationOutboxEvent, row.job_event_id)
        assert row.state == "manual_review" and row.stage_attempts["structure"] == 3
        assert row.transcript == TRANSCRIPT and event.status == "dead"
    assert calls == {"submit": 1, "poll": 1, "delete": 1, "structure": 3}


@pytest.mark.asyncio
async def test_google_disconnected_source_cannot_continue_provider_calls(context, monkeypatch):
    factory, actor, provider = context
    run, calls = await google_runner(context, monkeypatch, poll_results=[TRANSCRIPT])
    recording_id = await queue(context)
    await CallRecordingJobService.process_batch(worker_id="google-first", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        await CallDriveConnectionService.disconnect(session, actor)
    await make_google_event_available(factory, recording_id)
    await CallRecordingJobService.process_batch(worker_id="google-disconnected", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        row = await session.get(CallRecording, recording_id)
        assert row.state == "reconnect_required" and row.last_error_code == "call_drive_not_connected"
    assert calls["submit"] == 1 and calls["poll"] == calls["structure"] == 0
