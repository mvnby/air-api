"""Bounded image downloader used only by reviewed media repair plans."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 70_000_000
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 15.0
ALLOWED_CONTENT_TYPES = {
    "image/avif",
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


class ProductMediaDownloadBlockedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DownloadedProductMedia:
    source_url: str
    final_url: str
    content_type: str
    content: bytes
    content_hash: str
    width: int
    height: int


class BoundedProductMediaDownloader:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def download(
        self,
        url: str,
        *,
        allowed_hosts: tuple[str, ...],
    ) -> DownloadedProductMedia:
        hosts = {str(host).lower() for host in allowed_hosts}
        current = str(url or "").strip()
        if not hosts:
            raise ProductMediaDownloadBlockedError("Download host allowlist is empty")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_SECONDS),
            follow_redirects=False,
            headers={"User-Agent": "MVN reviewed product-media backfill/1"},
        )
        try:
            for redirect_count in range(MAX_REDIRECTS + 1):
                await self._validate_url(current, hosts)
                async with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count >= MAX_REDIRECTS:
                            raise ProductMediaDownloadBlockedError(
                                "Image redirect chain is invalid or too long"
                            )
                        current = urljoin(current, location)
                        continue
                    if response.status_code != 200:
                        raise ProductMediaDownloadBlockedError(
                            f"Image source returned HTTP {response.status_code}"
                        )
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        raise ProductMediaDownloadBlockedError(
                            "Image source content type is not allowed"
                        )
                    content_length = response.headers.get("content-length")
                    if content_length:
                        try:
                            declared_size = int(content_length)
                        except ValueError as exc:
                            raise ProductMediaDownloadBlockedError(
                                "Image source has an invalid content length"
                            ) from exc
                        if declared_size < 1 or declared_size > MAX_IMAGE_BYTES:
                            raise ProductMediaDownloadBlockedError(
                                "Image source exceeds the 20 MiB limit"
                            )
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_IMAGE_BYTES:
                            raise ProductMediaDownloadBlockedError(
                                "Image source exceeds the 20 MiB limit"
                            )
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    if not content:
                        raise ProductMediaDownloadBlockedError("Image source is empty")
                    width, height = await asyncio.to_thread(
                        self._validate_image_content,
                        content,
                    )
                    return DownloadedProductMedia(
                        source_url=str(url),
                        final_url=str(response.url),
                        content_type=content_type,
                        content=content,
                        content_hash=hashlib.sha256(content).hexdigest(),
                        width=width,
                        height=height,
                    )
            raise ProductMediaDownloadBlockedError("Image redirect chain is too long")
        except httpx.HTTPError as exc:
            raise ProductMediaDownloadBlockedError("Image download failed") from exc
        finally:
            if owns_client:
                await client.aclose()

    @classmethod
    async def _validate_url(cls, value: str, allowed_hosts: set[str]) -> None:
        parsed = urlsplit(value)
        hostname = str(parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or hostname not in allowed_hosts
            or parsed.username
            or parsed.password
            or parsed.port is not None
            or parsed.fragment
        ):
            raise ProductMediaDownloadBlockedError("Image URL is outside the reviewed boundary")
        try:
            addresses = await asyncio.to_thread(cls._resolve_addresses, hostname)
        except OSError as exc:
            raise ProductMediaDownloadBlockedError("Image host DNS lookup failed") from exc
        if not addresses:
            raise ProductMediaDownloadBlockedError("Image host did not resolve")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ProductMediaDownloadBlockedError(
                    "Image host resolved to a non-public address"
                )

    @staticmethod
    def _resolve_addresses(hostname: str) -> set[str]:
        return {
            str(item[4][0])
            for item in socket.getaddrinfo(
                hostname,
                443,
                type=socket.SOCK_STREAM,
            )
        }

    @staticmethod
    def _validate_image_content(content: bytes) -> tuple[int, int]:
        try:
            with Image.open(BytesIO(content)) as image:
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                    raise ProductMediaDownloadBlockedError(
                        "Image dimensions exceed the reviewed boundary"
                    )
                image.verify()
        except (UnidentifiedImageError, OSError) as exc:
            raise ProductMediaDownloadBlockedError(
                "Downloaded content is not a valid image"
            ) from exc
        return int(width), int(height)


__all__ = [
    "BoundedProductMediaDownloader",
    "DownloadedProductMedia",
    "ProductMediaDownloadBlockedError",
]
