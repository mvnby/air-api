"""Fetch and extract untrusted public source pages for Manager AI drafts."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup


_ALLOWED_CONTENT_TYPES = frozenset({"text/html", "text/plain"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_DEFAULT_PORTS = {"http": 80, "https": 443}


class ManagerContentSourceError(ValueError):
    """Safe source-fetch failure suitable for mapping to a client response."""

    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ExtractedContentSource:
    requested_url: str
    final_url: str
    title: str | None
    text: str


Resolver = Callable[[str, int], Awaitable[list[ipaddress.IPv4Address | ipaddress.IPv6Address]]]
ClientFactory = Callable[[], httpx.AsyncClient]


class ManagerContentSourceService:
    MAX_REDIRECTS = 3
    MAX_RESPONSE_BYTES = 1_500_000
    MAX_EXTRACTED_CHARS = 50_000
    USER_AGENT = "MVN-Manager-Content-Draft/1.0"

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._resolver = resolver or self._resolve_addresses
        self._client_factory = client_factory or self._default_client

    @staticmethod
    def _default_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        )

    async def fetch(self, source_url: str) -> ExtractedContentSource:
        requested_url = self._normalize_url(source_url)
        current_url = requested_url
        visited: set[str] = set()

        for redirect_count in range(self.MAX_REDIRECTS + 1):
            if current_url in visited:
                raise ManagerContentSourceError("Source redirect loop", code="redirect_loop")
            visited.add(current_url)

            parsed = urlsplit(current_url)
            hostname = str(parsed.hostname or "").rstrip(".").lower()
            port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
            addresses = await self._resolver(hostname, port)
            if not addresses:
                raise ManagerContentSourceError("Source hostname did not resolve", code="dns_failed")
            for address in addresses:
                self._require_public_address(address)

            async with self._request_once(
                public_url=current_url,
                pinned_address=addresses[0],
                hostname=hostname,
                port=port,
            ) as response:
                if response.status_code in _REDIRECT_STATUSES:
                    location = str(response.headers.get("location") or "").strip()
                    if not location:
                        raise ManagerContentSourceError(
                            "Source returned an invalid redirect",
                            code="invalid_redirect",
                        )
                    if redirect_count >= self.MAX_REDIRECTS:
                        raise ManagerContentSourceError(
                            "Source returned too many redirects",
                            code="too_many_redirects",
                        )
                    current_url = self._normalize_url(urljoin(current_url, location))
                    continue

                if response.status_code < 200 or response.status_code >= 300:
                    raise ManagerContentSourceError(
                        f"Source returned HTTP {response.status_code}",
                        code="source_http_error",
                    )

                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type not in _ALLOWED_CONTENT_TYPES:
                    raise ManagerContentSourceError(
                        "Source content type is not supported",
                        code="unsupported_content_type",
                    )
                content_encoding = response.headers.get("content-encoding", "").strip().lower()
                if content_encoding not in {"", "identity"}:
                    raise ManagerContentSourceError(
                        "Source content encoding is not supported",
                        code="unsupported_content_encoding",
                    )
                raw = await self._read_limited(response)
                encoding = response.encoding or "utf-8"
                try:
                    decoded = raw.decode(encoding, errors="replace")
                except LookupError:
                    decoded = raw.decode("utf-8", errors="replace")
                title, text = self._extract_readable_text(decoded, content_type=content_type)
                if not text:
                    raise ManagerContentSourceError(
                        "Source does not contain readable text",
                        code="empty_source",
                    )
                return ExtractedContentSource(
                    requested_url=requested_url,
                    final_url=current_url,
                    title=title,
                    text=text,
                )

        raise ManagerContentSourceError("Source returned too many redirects", code="too_many_redirects")

    @asynccontextmanager
    async def _request_once(
        self,
        *,
        public_url: str,
        pinned_address: ipaddress.IPv4Address | ipaddress.IPv6Address,
        hostname: str,
        port: int,
    ) -> AsyncIterator[httpx.Response]:
        public = httpx.URL(public_url)
        pinned = public.copy_with(host=str(pinned_address))
        default_port = _DEFAULT_PORTS[public.scheme]
        header_hostname = f"[{hostname}]" if ":" in hostname else hostname
        host_header = header_hostname if port == default_port else f"{header_hostname}:{port}"
        client = self._client_factory()
        try:
            request = client.build_request(
                "GET",
                pinned,
                headers={
                    "Accept": "text/html,text/plain;q=0.9",
                    "Accept-Encoding": "identity",
                    "Host": host_header,
                    "User-Agent": self.USER_AGENT,
                    "Connection": "close",
                },
                extensions={"sni_hostname": hostname},
            )
            response = await client.send(request, stream=True)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            await client.aclose()
            raise ManagerContentSourceError(
                "Source is temporarily unavailable",
                code="source_unavailable",
            ) from exc

        try:
            yield response
        finally:
            try:
                await response.aclose()
            finally:
                await client.aclose()

    async def _read_limited(self, response: httpx.Response) -> bytes:
        declared_size = response.headers.get("content-length")
        if declared_size:
            try:
                if int(declared_size) > self.MAX_RESPONSE_BYTES:
                    raise ManagerContentSourceError(
                        "Source response is too large",
                        code="source_too_large",
                    )
            except ValueError:
                pass

        chunks: list[bytes] = []
        size = 0
        if response.is_stream_consumed:
            if len(response.content) > self.MAX_RESPONSE_BYTES:
                raise ManagerContentSourceError(
                    "Source response is too large",
                    code="source_too_large",
                )
            return response.content
        try:
            async for chunk in response.aiter_raw():
                size += len(chunk)
                if size > self.MAX_RESPONSE_BYTES:
                    raise ManagerContentSourceError(
                        "Source response is too large",
                        code="source_too_large",
                    )
                chunks.append(chunk)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ManagerContentSourceError(
                "Source is temporarily unavailable",
                code="source_unavailable",
            ) from exc
        return b"".join(chunks)

    @classmethod
    def _normalize_url(cls, value: str) -> str:
        raw = str(value or "").strip()
        if len(raw) > 2048 or any(ord(character) < 32 or ord(character) == 127 for character in raw):
            raise ManagerContentSourceError("Invalid source URL", code="invalid_url")
        try:
            parsed = urlsplit(raw)
            port = parsed.port
        except ValueError as exc:
            raise ManagerContentSourceError("Invalid source URL", code="invalid_url") from exc

        if parsed.scheme.lower() not in _DEFAULT_PORTS:
            raise ManagerContentSourceError(
                "Only http and https source URLs are allowed",
                code="invalid_scheme",
            )
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ManagerContentSourceError("Invalid source URL", code="invalid_url")
        hostname = parsed.hostname.rstrip(".").lower()
        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise ManagerContentSourceError("Source address is not public", code="blocked_address")
        if port is not None and port not in {80, 443}:
            raise ManagerContentSourceError("Source port is not allowed", code="blocked_port")

        try:
            ascii_hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ManagerContentSourceError("Invalid source hostname", code="invalid_url") from exc
        netloc = ascii_hostname
        if ":" in ascii_hostname:
            netloc = f"[{ascii_hostname}]"
        if port is not None:
            netloc = f"{netloc}:{port}"
        normalized_url = urlunsplit(
            (parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, "")
        )
        try:
            httpx.URL(normalized_url)
        except (httpx.InvalidURL, UnicodeError, ValueError) as exc:
            raise ManagerContentSourceError("Invalid source URL", code="invalid_url") from exc
        return normalized_url

    @classmethod
    async def _resolve_addresses(
        cls,
        hostname: str,
        port: int,
    ) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        if literal is not None:
            return [literal]

        try:
            async with asyncio.timeout(5.0):
                records = await asyncio.to_thread(
                    socket.getaddrinfo,
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                    proto=socket.IPPROTO_TCP,
                )
        except TimeoutError as exc:
            raise ManagerContentSourceError(
                "Source hostname resolution timed out",
                code="dns_failed",
            ) from exc
        except socket.gaierror as exc:
            raise ManagerContentSourceError(
                "Source hostname did not resolve",
                code="dns_failed",
            ) from exc

        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        seen: set[str] = set()
        for record in records:
            raw_address = str(record[4][0]).split("%", 1)[0]
            address = ipaddress.ip_address(raw_address)
            if str(address) not in seen:
                seen.add(str(address))
                addresses.append(address)
        return addresses

    @staticmethod
    def _require_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
        normalized: ipaddress.IPv4Address | ipaddress.IPv6Address = address
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            normalized = address.ipv4_mapped
        if (
            not normalized.is_global
            or normalized.is_private
            or normalized.is_loopback
            or normalized.is_link_local
            or normalized.is_multicast
            or normalized.is_reserved
            or normalized.is_unspecified
        ):
            raise ManagerContentSourceError(
                "Source address is not public",
                code="blocked_address",
            )

    @classmethod
    def _extract_readable_text(cls, raw: str, *, content_type: str) -> tuple[str | None, str]:
        if content_type == "text/plain":
            return None, cls._normalize_text(raw)[: cls.MAX_EXTRACTED_CHARS]

        soup = BeautifulSoup(raw, "lxml")
        title = cls._normalize_text(soup.title.get_text(" ", strip=True)) if soup.title else None
        for node in soup.select(
            "script,style,noscript,template,svg,canvas,iframe,nav,footer,form,button,input"
        ):
            node.decompose()
        root: Any = soup.find("main") or soup.find("article") or soup.body or soup
        text = cls._normalize_text(root.get_text("\n", strip=True))
        return title or None, text[: cls.MAX_EXTRACTED_CHARS]

    @staticmethod
    def _normalize_text(value: str) -> str:
        lines = []
        for raw_line in str(value or "").replace("\r", "\n").split("\n"):
            line = re.sub(r"\s+", " ", raw_line).strip()
            if line and (not lines or line != lines[-1]):
                lines.append(line)
        return "\n".join(lines).strip()
