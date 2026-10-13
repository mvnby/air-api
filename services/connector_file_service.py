"""ChatGPT fileParams: fixed operator hosts, pinned DNS and bounded private bytes."""
import asyncio
import ipaddress
import socket
from io import BytesIO
from urllib.parse import urlsplit

import aiohttp
from aiohttp.abc import AbstractResolver
from PIL import Image

from core.config import settings
from schemas_connector_maintenance import OpenAIFile
from services.product_media_url_backfill_download import (
    BoundedProductMediaDownloader, ProductMediaDownloadBlockedError,
)

MAX_BYTES = 20 * 1024 * 1024
MIMES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


class ConnectorFileError(ValueError):
    """Safe error text contains no download URL, signed query or source content."""


class ConnectorFileUnavailable(RuntimeError):
    """Transient delivery failure; safe to retry the same file and command key."""


class _PinnedResolver(AbstractResolver):
    def __init__(self, host, addresses):
        self.host, self.addresses = host, addresses

    async def resolve(self, host, port=0, family=socket.AF_INET):
        if host != self.host or port != 443:
            raise ConnectorFileError("Unexpected file delivery host")
        return [dict(hostname=host, host=address, port=port,
                     family=socket.AF_INET6 if ":" in address else socket.AF_INET,
                     proto=socket.IPPROTO_TCP, flags=socket.AI_NUMERICHOST)
                for address in self.addresses]

    async def close(self):
        pass


class ConnectorFileService:
    @staticmethod
    def validate_source(file: OpenAIFile) -> str:
        try:
            parsed = urlsplit(file.download_url)
            host = parsed.hostname or ""
            allowed = set(settings.CONNECTOR_CHATGPT_FILE_HOSTS)
            if not allowed:
                raise ConnectorFileError("ChatGPT file upload is not configured; use private upload in Manager")
            if (parsed.scheme != "https" or host not in allowed or parsed.port is not None
                    or parsed.username is not None or parsed.password is not None or parsed.fragment
                    or not parsed.path or "\\" in file.download_url
                    or any(ch.isspace() or ord(ch) < 32 for ch in file.download_url)):
                raise ConnectorFileError("File source must be a supported ChatGPT file")
            # Operator configuration also fails closed for IPs, wildcards and URLs.
            if any(not item or "." not in item or item != item.lower() or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in item)
                   for item in allowed):
                raise ConnectorFileError("ChatGPT file delivery configuration is invalid")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                return host
            raise ConnectorFileError("File source must be a supported ChatGPT file")
        except ValueError as exc:
            if isinstance(exc, ConnectorFileError):
                raise
            raise ConnectorFileError("File source must be a supported ChatGPT file") from None

    @staticmethod
    async def public_addresses(host):
        try:
            result = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM), timeout=5)
            addresses = sorted({row[4][0] for row in result})
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise ConnectorFileError("ChatGPT file source resolved outside the public network")
            return addresses
        except (OSError, TimeoutError):
            raise ConnectorFileUnavailable("ChatGPT file delivery is unavailable; retry the same file and key") from None
        except ValueError as exc:
            if isinstance(exc, ConnectorFileError):
                raise
            raise ConnectorFileError("ChatGPT file source did not resolve to valid public addresses") from None

    @staticmethod
    def validate_image(content):
        try:
            BoundedProductMediaDownloader._validate_image_content(content)
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > 20_000_000:
                    raise ConnectorFileError("Photo dimensions exceed the configured limit")
                mime = MIMES.get(image.format)
                image.load()
            if mime is None:
                raise ConnectorFileError("Photo must be a JPEG, PNG or WebP image")
            return mime
        except (ProductMediaDownloadBlockedError, Image.DecompressionBombError, OSError, ValueError):
            raise ConnectorFileError("Photo must be a valid, bounded JPEG, PNG or WebP image") from None

    @classmethod
    async def _download_content(cls, file, *, limit, accept):
        host = cls.validate_source(file)
        addresses = await cls.public_addresses(host)
        resolver = _PinnedResolver(host, addresses)
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False, force_close=True)
        try:
            async with aiohttp.ClientSession(connector=connector, trust_env=False,
                    timeout=aiohttp.ClientTimeout(total=15, connect=5, sock_read=5),
                    headers={"Accept": accept}) as client:
                async with client.get(file.download_url, allow_redirects=False) as response:
                    if response.status == 429 or 500 <= response.status <= 599:
                        raise ConnectorFileUnavailable("ChatGPT file delivery is unavailable; retry the same file and key")
                    if response.status != 200:
                        raise ConnectorFileError("ChatGPT file link is unavailable; refresh the same file and retry the same key")
                    declared = response.content_length
                    if declared is not None and not 0 < declared <= limit:
                        raise ConnectorFileError("File exceeds the configured size limit")
                    chunks, size = [], 0
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        size += len(chunk)
                        if size > limit:
                            raise ConnectorFileError("File exceeds the configured size limit")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    if not content:
                        raise ConnectorFileError("File is empty")
                    declared_mime = response.headers.get("Content-Type", "").lower().split(";", 1)[0].strip()
                    return content, declared_mime
        except (aiohttp.ClientError, TimeoutError):
            raise ConnectorFileUnavailable("ChatGPT file delivery failed; retry the same file and key") from None
        except ValueError as exc:
            if isinstance(exc, ConnectorFileError):
                raise
            raise ConnectorFileError("ChatGPT file delivery returned an invalid response") from None

    @classmethod
    async def download(cls, file):
        content, declared_mime = await cls._download_content(
            file, limit=min(MAX_BYTES, settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES),
            accept="image/jpeg, image/png, image/webp",
        )
        mime = await asyncio.to_thread(cls.validate_image, content)
        supplied = file.mime_type.lower().split(";", 1)[0]
        if supplied and supplied != mime or declared_mime not in {mime, "application/octet-stream"}:
            raise ConnectorFileError("Photo type does not match its content")
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[mime]
        return content, file.file_name or f"{file.file_id}.{extension}", mime

    @classmethod
    async def download_attachment(cls, file):
        content, declared_mime = await cls._download_content(
            file, limit=min(10 * 1024 * 1024, settings.SERVICE_ATTACHMENT_MAX_SIZE_BYTES),
            accept="*/*",
        )
        supplied = file.mime_type.lower().split(";", 1)[0].strip()
        if supplied and supplied != "application/octet-stream" and declared_mime not in {
            supplied, "application/octet-stream",
        }:
            raise ConnectorFileError("File type does not match its ChatGPT metadata")
        return content
