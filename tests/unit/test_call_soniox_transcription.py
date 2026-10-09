import json
from types import SimpleNamespace

import httpx
import pytest

from services import call_soniox_transcription as soniox
from services.call_drive_provider import CallDriveError

FILE = "11111111-1111-4111-8111-111111111111"
JOB = "22222222-2222-4222-8222-222222222222"
SOURCE = "a" * 64
BASE = "https://api.eu.soniox.com"
MODEL = "stt-async-v5"
AUDIO = b"RIFF0000WAVEprivate-normalized-audio"
PRIVATE = "private-api-key-and-call-text"
ARGS = {"base_url": BASE, "model": MODEL}


@pytest.fixture
def configured(monkeypatch):
    config = SimpleNamespace(CALL_RECORDINGS_SONIOX_API_KEY=PRIVATE,
                             CALL_RECORDINGS_SONIOX_MODEL=MODEL,
                             CALL_RECORDINGS_SONIOX_API_BASE_URL=BASE)
    monkeypatch.setattr(soniox, "settings", config)
    return config


@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient
    seen = []
    def install(handler):
        def handle(request):
            seen.append(request)
            assert request.headers["authorization"] == f"Bearer {PRIVATE}"
            assert request.url.host == "api.eu.soniox.com"
            assert all(value <= 15 for value in request.extensions["timeout"].values())
            return handler(request)
        monkeypatch.setattr(soniox.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
        return seen
    return install


def detail(status="queued"):
    return {"id": JOB, "file_id": FILE, "model": MODEL, "status": status}


@pytest.mark.asyncio
async def test_private_upload_and_separate_async_submission(configured, transport):
    def handler(request):
        assert request.method == "POST"
        if request.url.path == "/v1/files":
            assert AUDIO in request.content and f"{SOURCE}.wav".encode() in request.content
            assert "multipart/form-data" in request.headers["content-type"]
            return httpx.Response(201, json={"id": FILE})
        assert request.url.path == "/v1/transcriptions"
        assert json.loads(request.content) == {"file_id": FILE, "model": MODEL, "language_hints": ["ru"], "client_reference_id": SOURCE}
        return httpx.Response(201, json=detail())
    seen = transport(handler)
    assert soniox.SonioxCallTranscriptionProvider.is_configured()
    assert await soniox.SonioxCallTranscriptionProvider.upload(content=AUDIO, source_id=SOURCE, **ARGS) == FILE
    assert await soniox.SonioxCallTranscriptionProvider.submit(file_id=FILE, source_id=SOURCE, **ARGS) == JOB
    assert len(seen) == 2 and all(b"drive.google" not in r.content for r in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "processing", "completed"])
async def test_poll_only_gets_saved_id(configured, transport, status):
    def handler(request):
        assert request.method == "GET"
        if request.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"id": JOB, "text": "  Нужен   звонок.\nЗавтра. ", "tokens": []})
        assert request.url.path == f"/v1/transcriptions/{JOB}"
        return httpx.Response(200, json=detail(status))
    seen = transport(handler)
    result = await soniox.SonioxCallTranscriptionProvider.poll(operation_name=JOB, file_id=FILE, **ARGS)
    assert result == ("Нужен звонок. Завтра." if status == "completed" else None)
    assert len(seen) == (2 if status == "completed" else 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(401,"call_soniox_access_denied"),(402,"call_soniox_provider_error"),(429,"call_soniox_provider_error"),(400,"call_soniox_invalid_audio"),(500,"call_soniox_submission_uncertain"),(302,"call_soniox_submission_uncertain")])
async def test_submission_statuses_are_safe_and_never_retried(configured, transport, status, expected):
    seen = transport(lambda request: httpx.Response(status, json={"message":PRIVATE}, headers={"Location":"https://evil.invalid"}))
    with pytest.raises(CallDriveError) as error:
        await soniox.SonioxCallTranscriptionProvider.submit(file_id=FILE, source_id=SOURCE, **ARGS)
    assert error.value.code == expected and PRIVATE not in str(error.value)
    assert len(seen) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "bad-json", "bad-id", "oversized"])
async def test_ambiguous_submit_response_requires_manual_review(configured, transport, failure):
    def handler(request):
        if failure == "timeout":
            raise httpx.ReadTimeout(PRIVATE, request=request)
        if failure == "bad-json":
            return httpx.Response(201, content=PRIVATE)
        if failure == "oversized":
            return httpx.Response(201, content=b"x"*(soniox.MAX_RESPONSE_BYTES+1))
        return httpx.Response(201, json={**detail(), "id":"../private"})
    seen = transport(handler)
    with pytest.raises(CallDriveError) as error:
        await soniox.SonioxCallTranscriptionProvider.submit(file_id=FILE, source_id=SOURCE, **ARGS)
    assert error.value.code == "call_soniox_submission_uncertain" and PRIVATE not in str(error.value)
    assert len(seen) == 1


@pytest.mark.parametrize("field,value", [("CALL_RECORDINGS_SONIOX_API_BASE_URL","http://api.soniox.com"),("CALL_RECORDINGS_SONIOX_API_BASE_URL","https://api.soniox.com/"),("CALL_RECORDINGS_SONIOX_API_BASE_URL","https://api.soniox.com@evil.invalid"),("CALL_RECORDINGS_SONIOX_MODEL","stt-async-v5/../"),("CALL_RECORDINGS_SONIOX_API_KEY","")])
def test_configuration_fails_closed(configured, field, value):
    setattr(configured, field, value)
    assert not soniox.SonioxCallTranscriptionProvider.is_configured()


@pytest.mark.asyncio
@pytest.mark.parametrize("file_id", ["../foreign", "https://evil.invalid/audio", "x"*200])
async def test_identifiers_reject_arbitrary_destinations_before_network(configured, transport, file_id):
    seen = transport(lambda request: pytest.fail("Must not call provider"))
    with pytest.raises(CallDriveError):
        await soniox.SonioxCallTranscriptionProvider.poll(operation_name=JOB, file_id=file_id, **ARGS)
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [{"id": JOB,"text":""},{"id":JOB,"text":"x"*12001},{"id":FILE,"text":"foreign"},{"id":JOB,"text":False}])
async def test_transcript_rejects_empty_overlong_or_foreign_material(configured, transport, response):
    transport(lambda req: httpx.Response(200, json=response if req.url.path.endswith("/transcript") else detail("completed")))
    with pytest.raises(CallDriveError):
        await soniox.SonioxCallTranscriptionProvider.poll(operation_name=JOB, file_id=FILE, **ARGS)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "error", "processing", "queued", "already-deleted"])
async def test_cleanup_addresses_only_own_terminal_objects(configured, transport, status):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(404) if status == "already-deleted" else httpx.Response(200, json=detail(status))
        assert request.method == "DELETE"
        assert request.url.path in {f"/v1/transcriptions/{JOB}", f"/v1/files/{FILE}"}
        return httpx.Response(204)
    seen = transport(handler)
    okay = await soniox.SonioxCallTranscriptionProvider.cleanup(operation_name=JOB, file_id=FILE, **ARGS)
    assert okay == (status in {"completed", "error", "already-deleted"})
    assert len(seen) == (2 if status == "already-deleted" else 3 if okay else 1)


@pytest.mark.asyncio
async def test_cleanup_does_not_delete_input_if_job_delete_fails(configured, transport):
    seen = transport(lambda req: httpx.Response(200, json=detail("completed")) if req.method == "GET" else httpx.Response(503, text=PRIVATE))
    assert not await soniox.SonioxCallTranscriptionProvider.cleanup(operation_name=JOB, file_id=FILE, **ARGS)
    assert len(seen) == 2 and all(req.url.path != f"/v1/files/{FILE}" for req in seen)
