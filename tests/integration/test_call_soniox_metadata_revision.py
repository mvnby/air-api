from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func
from sqlmodel import select

from models.call_recording import CallRecording
from services.call_drive_provider import CallDriveError
from services.call_recording_service import CallRecordingService
from services.call_recording_job_service import CallRecordingJobService
from tests.integration.test_call_recording_pipeline import (
    context, queue, soniox_runner, make_google_event_available, FILE_ID, TRANSCRIPT,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("transcript_saved", [False, True])
async def test_metadata_revision_waits_for_single_soniox_owner_then_reuses_result(context, monkeypatch, transcript_saved):
    factory, actor, provider = context
    run, calls = await soniox_runner(context, monkeypatch, poll_results=[TRANSCRIPT], cleanup_failures=1 if transcript_saved else 0)
    original_id = await queue(context)
    await CallRecordingJobService.process_batch(worker_id="single-soniox-owner", limit=1, session_factory=factory, runner=run)
    if transcript_saved:
        await make_google_event_available(factory, original_id)
        await CallRecordingJobService.process_batch(worker_id="soniox-before-cleanup", limit=1, session_factory=factory, runner=run)
    provider.version = "2"  # Same file and checksum, changed metadata only.
    async with factory() as session:
        with pytest.raises(CallDriveError) as error:
            await CallRecordingService.poll(session, actor, file_id=FILE_ID, provider=provider)
        assert error.value.code == "call_soniox_source_busy" and error.value.status_code == 409
        await session.rollback()
        result = await CallRecordingService.poll(session, actor, provider=provider)
        assert result.observed == result.queued == 0
        assert await session.scalar(select(func.count()).select_from(CallRecording)) == 1
    await make_google_event_available(factory, original_id)
    await CallRecordingJobService.process_batch(worker_id="soniox-finish-owner", limit=1, session_factory=factory, runner=run)
    async with factory() as session:
        original = await session.get(CallRecording, original_id)
        assert original.transcript == TRANSCRIPT and original.soniox_file_id is None
        now = datetime.now(timezone.utc)
        await CallRecordingService.poll(session, actor, file_id=FILE_ID, provider=provider, now=now)
        await CallRecordingService.poll(session, actor, file_id=FILE_ID, provider=provider, now=now + timedelta(seconds=61))
        newest = await session.scalar(select(CallRecording).order_by(CallRecording.id.desc()))
        assert newest.id != original_id and newest.transcript == TRANSCRIPT
        assert newest.soniox_file_id is newest.transcription_operation is None
    await CallRecordingJobService.process_batch(worker_id="metadata-reuses-result", limit=1, session_factory=factory, runner=run)
    assert calls["upload"] == calls["submit"] == calls["poll"] == 1
