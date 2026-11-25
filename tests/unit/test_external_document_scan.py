import asyncio
from struct import pack
from unittest.mock import AsyncMock, Mock

import pytest

from services import external_document_scan as scan
from services.document_upload_validation import EXTERNAL_DOCUMENT_MAX_BYTES


SOCKET_PATH = "/run/clamav/clamd.sock"


@pytest.fixture
def configured_scanner(monkeypatch):
    monkeypatch.setattr(scan.settings, "EXTERNAL_DOCUMENT_CLAMD_UNIX_SOCKET", SOCKET_PATH)


def _stream(reply):
    reader = asyncio.StreamReader(limit=scan._REPLY_LIMIT_BYTES)
    reader.feed_data(reply)
    reader.feed_eof()
    frames = []
    writer = Mock(write=Mock(side_effect=lambda frame: frames.append(bytes(frame))), drain=AsyncMock())
    return reader, writer, frames


@pytest.mark.asyncio
async def test_sends_original_bytes_as_bounded_clamd_frames(configured_scanner, monkeypatch):
    reader, writer, frames = _stream(b"stream: OK\0")
    connect = AsyncMock(return_value=(reader, writer))
    monkeypatch.setattr(scan.asyncio, "open_unix_connection", connect)

    first_chunk = b"a" * scan._CHUNK_BYTES
    second_chunk = b"document tail"
    await scan.scan_external_document(first_chunk + second_chunk)

    connect.assert_awaited_once_with(SOCKET_PATH, limit=scan._REPLY_LIMIT_BYTES)
    assert frames == [
        b"zINSTREAM\0", pack("!I", len(first_chunk)), first_chunk,
        pack("!I", len(second_chunk)), second_chunk, pack("!I", 0),
    ]
    writer.transport.abort.assert_called_once()


@pytest.mark.asyncio
async def test_rejects_detected_content_without_relaying_scanner_signature(configured_scanner, monkeypatch):
    reader, writer, _ = _stream(b"stream: Internal.Test.Signature FOUND\0")
    monkeypatch.setattr(scan.asyncio, "open_unix_connection", AsyncMock(return_value=(reader, writer)))

    with pytest.raises(scan.ExternalDocumentScanRejected, match="Файл отклонён") as failure:
        await scan.scan_external_document(b"document")

    assert "Internal.Test.Signature" not in str(failure.value)
    writer.transport.abort.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [
    b"INSTREAM size limit exceeded. ERROR\0",
    b"stream: OK",
    b"stream: OK\0unexpected second reply\0",
    b"x" * (scan._REPLY_LIMIT_BYTES + 10) + b"\0",
])
async def test_unexpected_or_partial_verdict_fails_closed(configured_scanner, monkeypatch, reply):
    reader, writer, _ = _stream(reply)
    monkeypatch.setattr(scan.asyncio, "open_unix_connection", AsyncMock(return_value=(reader, writer)))

    with pytest.raises(scan.ExternalDocumentScanUnavailable):
        await scan.scan_external_document(b"document")

    writer.transport.abort.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("environment, socket_path, required", [
    ("test", "", False),
    ("production", "", True),
    ("test", "relative/clamd.sock", True),
])
async def test_scanner_configuration_is_required_for_production_uploads(monkeypatch, environment, socket_path, required):
    monkeypatch.setattr(scan.settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(scan.settings, "EXTERNAL_DOCUMENT_CLAMD_UNIX_SOCKET", socket_path)
    connect = AsyncMock()
    monkeypatch.setattr(scan.asyncio, "open_unix_connection", connect)

    if required:
        with pytest.raises(scan.ExternalDocumentScanUnavailable, match="не настроена"):
            await scan.scan_external_document(b"document")
    else:
        await scan.scan_external_document(b"document")

    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_rejects_empty_and_oversize_files_before_connecting(configured_scanner, monkeypatch):
    connect = AsyncMock()
    monkeypatch.setattr(scan.asyncio, "open_unix_connection", connect)

    for content in (b"", b"x" * (EXTERNAL_DOCUMENT_MAX_BYTES + 1)):
        with pytest.raises(ValueError, match="Размер файла"):
            await scan.scan_external_document(content)

    connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_socket_error_or_timeout_is_unavailable(configured_scanner, monkeypatch):
    connect = AsyncMock(side_effect=FileNotFoundError(SOCKET_PATH))
    monkeypatch.setattr(scan.asyncio, "open_unix_connection", connect)

    with pytest.raises(scan.ExternalDocumentScanUnavailable) as failure:
        await scan.scan_external_document(b"document")
    assert SOCKET_PATH not in str(failure.value)

    async def never_connect(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(scan, "_SCAN_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(scan.asyncio, "open_unix_connection", never_connect)
    with pytest.raises(scan.ExternalDocumentScanUnavailable):
        await scan.scan_external_document(b"document")


@pytest.mark.asyncio
async def test_scans_are_bounded_without_waiting_queue(configured_scanner, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def connect(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            entered.set()
        await release.wait()
        reader, writer, _ = _stream(b"stream: OK\0")
        return reader, writer

    monkeypatch.setattr(scan.asyncio, "open_unix_connection", connect)
    active = [asyncio.create_task(scan.scan_external_document(b"document")) for _ in range(2)]
    try:
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(scan.ExternalDocumentScanUnavailable):
            await scan.scan_external_document(b"excess document")
        assert count == 2
    finally:
        release.set()
        await asyncio.gather(*active)

    await scan.scan_external_document(b"next document")
    assert count == 3
