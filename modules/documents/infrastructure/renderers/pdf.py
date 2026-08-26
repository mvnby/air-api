"""Optional PDF conversion boundary for native documents.

The document module does not silently depend on LibreOffice or Gotenberg.
Callers choose a converter explicitly and can surface its health in a future
manager endpoint or background-job status.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True, slots=True)
class PdfConverterHealth:
    available: bool
    provider: str
    detail: str


class PdfConversionError(RuntimeError):
    pass


class PdfConversionUnavailableError(PdfConversionError):
    pass


class PdfConverter(Protocol):
    def health(self) -> PdfConverterHealth: ...

    def convert_docx(
        self, content: bytes, *, filename: str = "document.docx"
    ) -> bytes: ...


class UnavailablePdfConverter:
    """A safe default which makes skipped PDF conversion observable."""

    def __init__(
        self, reason: str = "No PDF conversion provider is configured"
    ) -> None:
        self.reason = reason

    def health(self) -> PdfConverterHealth:
        return PdfConverterHealth(
            available=False, provider="unconfigured", detail=self.reason
        )

    def convert_docx(self, content: bytes, *, filename: str = "document.docx") -> bytes:
        raise PdfConversionUnavailableError(self.reason)


class GotenbergPdfConverter:
    """Explicit Gotenberg adapter; it never starts or assumes a local service."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        if not base_url:
            raise ValueError("Gotenberg base_url is required")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> PdfConverterHealth:
        try:
            response = httpx.get(
                f"{self.base_url}/health", timeout=self.timeout_seconds
            )
        except httpx.HTTPError as exc:
            return PdfConverterHealth(False, "gotenberg", f"unreachable: {exc}")
        if response.is_success:
            return PdfConverterHealth(True, "gotenberg", "healthy")
        return PdfConverterHealth(
            False, "gotenberg", f"health endpoint returned HTTP {response.status_code}"
        )

    def convert_docx(self, content: bytes, *, filename: str = "document.docx") -> bytes:
        try:
            response = httpx.post(
                f"{self.base_url}/forms/libreoffice/convert",
                files={
                    "files": (
                        filename,
                        content,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise PdfConversionError(
                f"Gotenberg DOCX-to-PDF conversion failed: {exc}"
            ) from exc
        if not response.content.startswith(b"%PDF-"):
            raise PdfConversionError("Gotenberg returned content that is not a PDF")
        return response.content
