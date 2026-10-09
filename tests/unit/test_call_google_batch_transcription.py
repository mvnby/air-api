import asyncio
import json
import threading
import traceback
from types import SimpleNamespace

import httpx
import pytest
import requests
from google.auth.exceptions import RefreshError

from services import call_google_batch_transcription as batch
from services.call_drive_provider import CallDriveError

SOURCE_ID = "b" * 64
PROJECT = "test-project"
BUCKET = "private-call-tests"
OPERATION = f"projects/{PROJECT}/locations/eu/operations/op-safe-001"
URI = f"gs://{BUCKET}/call-recordings/{SOURCE_ID}.wav"
AUDIO = b"RIFF0000WAVEtest-normalized-audio"
PRIVATE_MARKER = "secret-key-and-private-call-material"


@pytest.fixture
def configured(monkeypatch, tmp_path):
    path = tmp_path / "dedicated-call-service-account.json"
    info = {"type": "service_account", "client_email": "calls@test-project.iam.gserviceaccount.com", "private_key": "test-key", "token_uri": batch.TOKEN_URL}
    path.write_text(json.dumps(info))
    config = SimpleNamespace(
        CALL_RECORDINGS_GOOGLE_CREDENTIALS_FILE=str(path),
        CALL_RECORDINGS_GOOGLE_PROJECT_ID=PROJECT,
        CALL_RECORDINGS_GOOGLE_BUCKET=BUCKET,
        CALL_RECORDINGS_GOOGLE_LOCATION="eu",
        CALL_RECORDINGS_GOOGLE_MODEL="chirp_3",
    )
    monkeypatch.setattr(batch, "settings", config)

    class Credentials:
        token = None
        def refresh(self, request):
            self.token = "test-only-token"
    monkeypatch.setattr(batch.service_account.Credentials, "from_service_account_info", lambda info, scopes: Credentials())
    return config, path


@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient
    seen = []
    def install(handler):
        async def handle(request):
            seen.append(request)
            assert request.headers["authorization"] == "Bearer test-only-token"
            assert all(timeout <= 15 for timeout in request.extensions["timeout"].values())
            response = handler(request)
            return await response if hasattr(response, "__await__") else response
        monkeypatch.setattr(batch.httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
        return seen
    return install


def completed(*texts):
    return {"name": OPERATION, "done": True, "response": {"results": {URI: {"inlineResult": {"transcript": {"results": [{"alternatives": [{"transcript": text}]} for text in texts]}}}}}}


@pytest.mark.asyncio
async def test_submit_is_one_private_dynamic_batch_with_conditional_deterministic_upload(configured, transport):
    uploads = 0
    def handle(request):
        nonlocal uploads
        assert request.method == "POST"
        if request.url.host == "storage.googleapis.com":
            uploads += 1
            assert request.url.path == f"/upload/storage/v1/b/{BUCKET}/o"
            assert dict(request.url.params) == {"uploadType": "media", "name": f"call-recordings/{SOURCE_ID}.wav", "ifGenerationMatch": "0"}
            assert request.headers["content-type"] == "audio/wav" and request.content == AUDIO
            # The configured bucket supplies private IAM, including uniform
            # bucket access. No public ACL or filename/contact is transmitted.
            assert "predefinedAcl" not in request.url.params
            return httpx.Response(200 if uploads == 1 else 412)
        assert request.url.host == "eu-speech.googleapis.com"
        assert request.url.path == f"/v2/projects/{PROJECT}/locations/eu/recognizers/_:batchRecognize"
        assert json.loads(request.content) == {
            "config": {"autoDecodingConfig": {}, "languageCodes": ["ru-RU"], "model": "chirp_3"},
            "files": [{"uri": URI}], "recognitionOutputConfig": {"inlineResponseConfig": {}},
            "processingStrategy": "DYNAMIC_BATCHING",
        }
        return httpx.Response(200, json={"name": OPERATION})
    seen = transport(handle)
    assert batch.GoogleCallBatchTranscriptionProvider.is_configured()
    assert await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID) == OPERATION
    # A caller retry cannot overwrite the existing object. Each invocation
    # submits only once; the durable caller polls instead after saving its name.
    assert await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID) == OPERATION
    assert len(seen) == 4 and uploads == 2


@pytest.mark.asyncio
async def test_poll_pending_then_exact_inline_result_only_gets_saved_operation(configured, transport):
    responses = [{"name": OPERATION}, {"name": OPERATION, "done": False}, completed("  Нужно\nобслуживание ", " завтра   утром. ")]
    def handle(request):
        assert request.method == "GET" and str(request.url) == f"https://eu-speech.googleapis.com/v2/{OPERATION}"
        return httpx.Response(200, json=responses.pop(0))
    seen = transport(handle)
    assert await batch.GoogleCallBatchTranscriptionProvider.poll(operation_name=OPERATION, source_id=SOURCE_ID) is None
    assert await batch.GoogleCallBatchTranscriptionProvider.poll(operation_name=OPERATION, source_id=SOURCE_ID) is None
    assert await batch.GoogleCallBatchTranscriptionProvider.poll(operation_name=OPERATION, source_id=SOURCE_ID) == "Нужно обслуживание завтра утром."
    assert len(seen) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["https://example.invalid/audio", "projects/another-project/locations/eu/operations/op", "projects/test-project/locations/us/operations/op", "projects/test-project/locations/eu/operations/../../secret", "projects/test-project/locations/eu/operations/op?key=secret"])
async def test_poll_rejects_other_project_location_or_arbitrary_destination_before_auth(configured, transport, operation):
    seen = transport(lambda request: pytest.fail("Must not make a request"))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.poll(operation_name=operation, source_id=SOURCE_ID)
    assert error.value.code == "call_google_operation_failed" and not seen


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["empty", "not_wav", "too_large", "nonbytes", "nonopaque_source"])
async def test_invalid_input_cannot_upload(configured, transport, case):
    content, source = AUDIO, SOURCE_ID
    if case == "empty": content = b""
    elif case == "not_wav": content = b"personal-nonaudio-content"
    elif case == "too_large": content = b"RIFF0000WAVE" + b"x" * batch.MAX_AUDIO_BYTES
    elif case == "nonbytes": content = bytearray(AUDIO)
    else: source = "caller-phone-or-name.wav"
    seen = transport(lambda request: pytest.fail("Must not make a request"))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=content, source_id=source)
    assert error.value.code == "call_google_invalid_audio" and not seen


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("CALL_RECORDINGS_GOOGLE_LOCATION", "https://example.invalid"), ("CALL_RECORDINGS_GOOGLE_LOCATION", "global"), ("CALL_RECORDINGS_GOOGLE_BUCKET", "bucket/../other"), ("CALL_RECORDINGS_GOOGLE_PROJECT_ID", "project?billing=other"), ("CALL_RECORDINGS_GOOGLE_MODEL", "chirp_3/other"), ("CALL_RECORDINGS_GOOGLE_CREDENTIALS_FILE", "")])
async def test_configuration_is_bound_and_has_no_vision_or_default_credential_fallback(configured, transport, field, value):
    config, path = configured
    setattr(config, field, value)
    config.GOOGLE_VISION_CREDENTIALS_FILE = str(path)
    seen = transport(lambda request: pytest.fail("Must not make a request"))
    assert not batch.GoogleCallBatchTranscriptionProvider.is_configured()
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID)
    assert error.value.code == "call_google_not_configured" and not seen


@pytest.mark.parametrize("changes", [{"type": "external_account"}, {"token_uri": "https://example.invalid/token"}, {"universe_domain": "example.invalid"}, {"private_key": ""}])
def test_configuration_requires_service_account_and_fixed_google_auth_endpoint(configured, changes):
    config, path = configured
    info = json.loads(path.read_text())
    path.write_text(json.dumps({**info, **changes}))
    assert not batch.GoogleCallBatchTranscriptionProvider.is_configured()


@pytest.mark.asyncio
async def test_auth_refresh_uses_dedicated_service_account_cloud_scope_thread_and_bounded_transport(configured, transport, monkeypatch):
    main_thread = threading.get_ident()
    refresh_calls = []
    def request(session, method, url, **kwargs):
        assert threading.get_ident() != main_thread
        assert url == batch.TOKEN_URL and kwargs["timeout"] == 15
        assert kwargs["allow_redirects"] is False and session.trust_env is False
        refresh_calls.append(url)
        response = requests.Response()
        response.status_code, response._content = 200, b"{}"
        return response
    monkeypatch.setattr(requests.Session, "request", request)
    class Credentials:
        token = None
        def refresh(self, request):
            request(url=batch.TOKEN_URL, method="POST", timeout=120)
            self.token = "test-only-token"
    def load(info, scopes):
        assert threading.get_ident() != main_thread
        assert info["client_email"] == "calls@test-project.iam.gserviceaccount.com"
        assert scopes == ("https://www.googleapis.com/auth/cloud-platform",)
        return Credentials()
    monkeypatch.setattr(batch.service_account.Credentials, "from_service_account_info", load)
    transport(lambda request: httpx.Response(200, json={"name": OPERATION}))
    assert await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID) == OPERATION
    assert refresh_calls == [batch.TOKEN_URL]


@pytest.mark.asyncio
async def test_auth_and_http_errors_do_not_leak_provider_or_credential_material(configured, transport, monkeypatch, caplog):
    class Credentials:
        def refresh(self, request):
            raise RefreshError(PRIVATE_MARKER)
    monkeypatch.setattr(batch.service_account.Credentials, "from_service_account_info", lambda info, scopes: Credentials())
    seen = transport(lambda request: pytest.fail("No API request after auth rejection"))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID)
    assert error.value.code == "call_google_access_denied" and not seen
    assert PRIVATE_MARKER not in "".join(traceback.format_exception(error.value))
    assert PRIVATE_MARKER not in caplog.text


@pytest.mark.asyncio
async def test_invalid_private_key_is_unconfigured_without_api_calls_or_error_leaks(configured, transport, monkeypatch):
    def reject(info, scopes):
        raise ValueError(PRIVATE_MARKER)
    monkeypatch.setattr(batch.service_account.Credentials, "from_service_account_info", reject)
    seen = transport(lambda request: pytest.fail("No API call with an invalid key"))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID)
    assert error.value.code == "call_google_not_configured" and not seen
    assert PRIVATE_MARKER not in "".join(traceback.format_exception(error.value))


@pytest.mark.asyncio
async def test_http_transport_timeout_is_sanitized_and_cleanup_remains_best_effort(configured, transport):
    def timeout(request):
        raise httpx.ReadTimeout(PRIVATE_MARKER, request=request)
    seen = transport(timeout)
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.poll(operation_name=OPERATION, source_id=SOURCE_ID)
    assert error.value.code == "call_google_provider_error" and len(seen) == 1
    assert PRIVATE_MARKER not in "".join(traceback.format_exception(error.value))
    assert not await batch.GoogleCallBatchTranscriptionProvider.delete_audio(source_id=SOURCE_ID)
    assert len(seen) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code", [(401, "call_google_access_denied"), (403, "call_google_access_denied"), (429, "call_google_provider_error"), (503, "call_google_provider_error"), (413, "call_google_invalid_audio"), (307, "call_google_provider_error")])
async def test_http_errors_are_sanitized_and_never_retried_or_redirected(configured, transport, status, code):
    seen = transport(lambda request: httpx.Response(status, json={"error": {"message": PRIVATE_MARKER}}, headers={"Location": "https://example.invalid/private-audio"}))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID)
    assert error.value.code == code and len(seen) == 1
    assert PRIVATE_MARKER not in "".join(traceback.format_exception(error.value))


@pytest.mark.asyncio
async def test_speech_post_failure_is_not_retried_after_successful_upload(configured, transport):
    seen = transport(lambda request: httpx.Response(200) if request.url.host == "storage.googleapis.com" else httpx.Response(503, text=PRIVATE_MARKER))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID)
    assert error.value.code == "call_google_provider_error" and len(seen) == 2
    assert PRIVATE_MARKER not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("response,code", [
    ([], "call_google_provider_error"),
    ({"name": OPERATION, "done": "true"}, "call_google_provider_error"),
    ({"name": OPERATION, "done": True}, "call_google_provider_error"),
    ({"name": OPERATION, "done": False, "response": {}}, "call_google_provider_error"),
    ({"name": "wrong-operation", "done": False}, "call_google_provider_error"),
    ({"name": OPERATION, "done": True, "error": {"code": 13, "message": PRIVATE_MARKER}}, "call_google_operation_failed"),
    ({"name": OPERATION, "done": True, "response": {"results": {URI: {"error": {"code": 3, "message": PRIVATE_MARKER}}}}}, "call_google_operation_failed"),
    ({"name": OPERATION, "done": True, "response": {"results": {"gs://another/audio.wav": {}}}}, "call_google_provider_error"),
    ({"name": OPERATION, "done": True, "response": {"results": {URI: {}, "gs://another/audio.wav": {}}}}, "call_google_provider_error"),
    ({"name": OPERATION, "done": True, "response": {"results": {URI: {"transcript": {"results": []}}}}}, "call_google_provider_error"),
    (completed(123), "call_google_provider_error"),
    (completed(), "call_google_invalid_audio"),
    (completed(" " * 20), "call_google_invalid_audio"),
    (completed("я" * 12001), "call_google_provider_error"),
])
async def test_poll_fails_closed_on_wrong_file_or_malformed_nonempty_bounded_output(configured, transport, response, code):
    seen = transport(lambda request: httpx.Response(200, json=response))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.poll(operation_name=OPERATION, source_id=SOURCE_ID)
    assert error.value.code == code and len(seen) == 1
    assert PRIVATE_MARKER not in str(error.value)


@pytest.mark.asyncio
async def test_json_body_and_entire_method_are_bounded(configured, transport, monkeypatch):
    monkeypatch.setattr(batch, "MAX_RESPONSE_BYTES", 64)
    transport(lambda request: httpx.Response(200, content=b"x" * 65))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.poll(operation_name=OPERATION, source_id=SOURCE_ID)
    assert error.value.code == "call_google_provider_error"
    monkeypatch.setattr(batch, "METHOD_TIMEOUT_SECONDS", 0.01)
    async def slow(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json={"name": OPERATION})
    seen = transport(slow)
    seen.clear()
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID)
    assert error.value.code == "call_google_provider_error" and len(seen) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status,success", [(204, True), (404, True), (403, False), (503, False)])
async def test_cleanup_deletes_only_own_deterministic_object_best_effort(configured, transport, status, success):
    def handle(request):
        assert request.method == "DELETE" and request.url.host == "storage.googleapis.com"
        assert request.url.raw_path == f"/storage/v1/b/{BUCKET}/o/call-recordings%2F{SOURCE_ID}.wav".encode()
        return httpx.Response(status, text=PRIVATE_MARKER if status >= 400 else "")
    seen = transport(handle)
    assert await batch.GoogleCallBatchTranscriptionProvider.delete_audio(source_id=SOURCE_ID) is success
    assert len(seen) == 1
    assert not await batch.GoogleCallBatchTranscriptionProvider.delete_audio(source_id="../another-person.wav")
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_us_is_the_only_other_speech_host_and_operation_is_project_bound(configured, transport):
    config, path = configured
    config.CALL_RECORDINGS_GOOGLE_LOCATION = "us"
    operation = OPERATION.replace("/eu/", "/us/")
    def handle(request):
        assert request.url.host in {"storage.googleapis.com", "us-speech.googleapis.com"}
        return httpx.Response(200, json={"name": operation})
    seen = transport(handle)
    assert await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID) == operation
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_submit_refuses_untrusted_operation_returned_by_provider(configured, transport):
    seen = transport(lambda request: httpx.Response(200, json={"name": "projects/other-project/locations/eu/operations/evil"}))
    with pytest.raises(CallDriveError) as error:
        await batch.GoogleCallBatchTranscriptionProvider.submit(content=AUDIO, source_id=SOURCE_ID)
    assert error.value.code == "call_google_provider_error" and len(seen) == 2
