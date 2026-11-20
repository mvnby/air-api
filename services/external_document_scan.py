"""Screen typed external order uploads with a local ClamAV daemon."""

import asyncio
from pathlib import PurePosixPath
from struct import pack

from core.config import settings
from services.document_upload_validation import (
    EXTERNAL_DOCUMENT_MAX_BYTES,
    ExternalDocumentValidationUnavailable,
)


_SCAN_TIMEOUT_SECONDS = 8.0
_CHUNK_BYTES = 64 * 1024
_REPLY_LIMIT_BYTES = 1024
_scan_slots = asyncio.Semaphore(2)
_UNAVAILABLE = "Антивирусная проверка файлов временно недоступна. Повторите загрузку."


class ExternalDocumentScanUnavailable(ExternalDocumentValidationUnavailable):
    """The scanner could not return a complete verdict."""


class ExternalDocumentScanRejected(ValueError):
    """The scanner rejected the upload."""


async def _scan_clamd(socket_path: str, content: bytes) -> None:
    reader, writer = await asyncio.open_unix_connection(socket_path, limit=_REPLY_LIMIT_BYTES)
    try:
        writer.write(b"zINSTREAM\0")
        data = memoryview(content)
        for offset in range(0, len(data), _CHUNK_BYTES):
            chunk = data[offset:offset + _CHUNK_BYTES]
            writer.write(pack("!I", len(chunk)))
            writer.write(chunk)
            await writer.drain()
        writer.write(pack("!I", 0))
        await writer.drain()

        reply = await reader.readuntil(b"\0")
        if reply.startswith(b"stream: ") and reply.endswith(b" FOUND\0"):
            raise ExternalDocumentScanRejected("Файл отклонён антивирусной проверкой.")
        if reply != b"stream: OK\0" or await reader.read(1):
            raise ExternalDocumentScanUnavailable(_UNAVAILABLE)
    finally:
        # Abort also discards backlogged frames after a timeout or cancellation.
        writer.transport.abort()


async def scan_external_document(content: bytes) -> None:
    """Submit only bounded bytes and require a clean verdict when scanning is active."""
    if not isinstance(content, bytes) or not 0 < len(content) <= EXTERNAL_DOCUMENT_MAX_BYTES:
        raise ValueError("Размер файла должен быть от 1 байта до 10 МБ.")

    socket_path = settings.EXTERNAL_DOCUMENT_CLAMD_UNIX_SOCKET.strip()
    if not socket_path and not settings.is_production:
        return
    if not socket_path or "\0" in socket_path or not PurePosixPath(socket_path).is_absolute():
        raise ExternalDocumentScanUnavailable("Антивирусная проверка файлов не настроена.")

    # Decline excess requests before acquiring a slot so upload buffers do not
    # accumulate while the daemon is busy.
    if _scan_slots.locked():
        raise ExternalDocumentScanUnavailable(_UNAVAILABLE)

    try:
        async with _scan_slots, asyncio.timeout(_SCAN_TIMEOUT_SECONDS):
            await _scan_clamd(socket_path, content)
    except (OSError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise ExternalDocumentScanUnavailable(_UNAVAILABLE) from exc
