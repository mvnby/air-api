"""Catalog reference documents; separate from order/business documents."""

import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.input_validation import validate_public_manual_url


CatalogDocumentTarget = Literal["brand", "series", "product"]
CatalogDocumentKind = Literal["catalog", "operation", "installation", "service", "brochure", "certificate", "other"]


def normalize_catalog_document_url(value: str) -> str:
    """Validate references without requesting their content or resolving DNS.

    Future server-side readers must also resolve/check every destination and
    redirect at fetch time, as the content-source reader already does.
    """
    candidate = validate_public_manual_url(value)
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Некорректная ссылка на документ") from exc
    if not parsed.scheme:
        return candidate
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if port not in {None, 80, 443}:
        raise ValueError("Ссылка на документ должна использовать обычный HTTP(S) порт")
    if (
        not hostname
        or "." not in hostname and ":" not in hostname
        or hostname.endswith((".localhost", ".local", ".internal", ".lan", ".home", ".test", ".invalid"))
    ):
        raise ValueError("Ссылка на документ должна вести на публичный сайт")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if hostname.replace(".", "").isdigit() or hostname.startswith("0x"):
            raise ValueError("Неоднозначный адрес документа")
        try:
            hostname = hostname.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("Некорректный адрес документа") from exc
        if len(hostname) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in hostname.split(".")):
            raise ValueError("Некорректный адрес документа")
    else:
        if not address.is_global or getattr(address, "ipv4_mapped", None) and not address.ipv4_mapped.is_global:
            raise ValueError("Ссылка на документ должна вести на публичный сайт")
        hostname = address.compressed
    netloc = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and not (parsed.scheme == "https" and port == 443 or parsed.scheme == "http" and port == 80):
        netloc = f"{netloc}:{port}"
    result = urlunsplit((parsed.scheme, netloc, parsed.path or "/", parsed.query, ""))
    if len(result) > 2048:
        raise ValueError("Ссылка на документ слишком длинная")
    return result


class CatalogDocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=250)
    url: str = Field(min_length=1, max_length=2048)
    kind: CatalogDocumentKind = "other"
    source_url: str | None = Field(default=None, max_length=2048)
    language: str | None = Field(default=None, max_length=16, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})?$")
    year: int | None = Field(default=None, ge=1900, le=2200)
    visibility: Literal["public", "internal"] = "public"
    inherit_to_products: bool = True

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return normalize_catalog_document_url(value)

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        result = normalize_catalog_document_url(value)
        if not urlsplit(result).scheme:
            raise ValueError("Источник должен быть HTTP(S) ссылкой")
        return result


class CatalogDocumentsReplacePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[CatalogDocumentInput] = Field(default_factory=list, max_length=100)


class CatalogDocumentResponse(CatalogDocumentInput):
    id: int
    origin_type: CatalogDocumentTarget
    origin_id: int
    origin_title: str
    inherited: bool = False


class CatalogDocumentWorkspace(BaseModel):
    own: list[CatalogDocumentResponse] = Field(default_factory=list)
    inherited: list[CatalogDocumentResponse] = Field(default_factory=list)
    effective: list[CatalogDocumentResponse] = Field(default_factory=list)


class CatalogDocumentUploadResponse(BaseModel):
    url: str
    title: str
