from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import math
import mimetypes
import os
import re
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError, features
from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import (
    Article,
    Brand,
    MediaAsset,
    Product,
    ProductAttachment,
    ProductImage,
    ProductImageVariant,
    ProductSeries,
    Service,
)
from services.general_media_storage_service import get_general_media_storage
from services.product_image_processing_contract import ProductImageVariantType
from services.product_image_processing_provider import (
    ProductImageProcessingContext,
    get_product_image_processor,
)


MEDIA_LIBRARY_BASE_DIR = Path("media/library")
MEDIA_LIBRARY_PUBLIC_PREFIX = "/media/library"
MAX_LIBRARY_IMAGE_PIXELS = 50_000_000
MAX_REMOTE_IMAGE_BYTES = 20 * 1024 * 1024
REMOTE_IMAGE_TIMEOUT_SECONDS = 12.0
SVG_MIME_TYPE = "image/svg+xml"
SVG_FORBIDDEN_TAGS = {"script", "foreignobject", "iframe", "object", "embed"}
ALLOWED_KINDS = {
    "product",
    "article",
    "service",
    "installation",
    "strobe",
    "brand",
    "misc",
}


@dataclass(frozen=True)
class StoredLibraryImage:
    url: str
    path: str
    content_hash: str
    width: int
    height: int
    size_bytes: int
    mime_type: str = "image/webp"
    storage_provider: str = "local"


@dataclass(frozen=True)
class ExistingMediaReference:
    url: str
    kind: str
    title: str
    variant_type: str
    tags: tuple[str, ...]


class MediaLibraryService:
    @staticmethod
    async def list_assets(
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 40,
        query: str | None = None,
        kind: str | None = None,
        tag: str | None = None,
        status: str | None = None,
    ) -> dict:
        safe_page = max(1, int(page or 1))
        safe_limit = max(1, min(int(limit or 40), 100))

        stmt = select(MediaAsset)
        conditions = []
        q = (query or "").strip()
        if q:
            pattern = f"%{q}%"
            conditions.append(
                or_(
                    MediaAsset.title.ilike(pattern),
                    MediaAsset.alt_text.ilike(pattern),
                    MediaAsset.description.ilike(pattern),
                    MediaAsset.source_filename.ilike(pattern),
                )
            )
        if kind:
            conditions.append(MediaAsset.kind == MediaLibraryService._normalize_kind(kind))
        if status:
            conditions.append(MediaAsset.processing_status == status)
        for condition in conditions:
            stmt = stmt.where(condition)

        rows = (await session.execute(stmt.order_by(MediaAsset.created_at.desc()))).scalars().all()
        normalized_tag = MediaLibraryService._normalize_tag(tag) if tag else ""
        if normalized_tag:
            rows = [
                row
                for row in rows
                if normalized_tag in {MediaLibraryService._normalize_tag(item) for item in row.tags or []}
            ]

        total = len(rows)
        start = (safe_page - 1) * safe_limit
        page_rows = rows[start : start + safe_limit]
        items = [await MediaLibraryService.serialize_asset(session, item) for item in page_rows]
        return {
            "items": items,
            "meta": {
                "total": total,
                "page": safe_page,
                "limit": safe_limit,
                "pages": math.ceil(total / safe_limit) if total else 1,
            },
        }

    @staticmethod
    async def upload_assets(
        session: AsyncSession,
        *,
        files: Iterable[tuple[str | None, bytes]],
        kind: str,
        tags: list[str] | None,
        created_by: str | None,
    ) -> dict:
        assets: list[MediaAsset] = []
        for filename, content in files:
            if not content:
                continue
            stored = await MediaLibraryService._store_image(
                content,
                variant_type="original",
            )
            asset = MediaAsset(
                title=MediaLibraryService._title_from_filename(filename) or "Без названия",
                kind=MediaLibraryService._normalize_kind(kind),
                tags=MediaLibraryService._normalize_tags(tags),
                variant_type="original",
                url=stored.url,
                original_url=stored.url,
                source_filename=filename,
                mime_type=stored.mime_type,
                storage_provider=stored.storage_provider,
                processing_status="ready",
                content_hash=stored.content_hash,
                width=stored.width,
                height=stored.height,
                size_bytes=stored.size_bytes,
                created_by=created_by,
            )
            session.add(asset)
            assets.append(asset)

        if not assets:
            raise ValueError("No valid image files uploaded")

        await session.commit()
        for asset in assets:
            await session.refresh(asset)
        return {
            "uploaded": len(assets),
            "items": [await MediaLibraryService.serialize_asset(session, asset) for asset in assets],
        }

    @staticmethod
    async def upload_asset_from_url(
        session: AsyncSession,
        *,
        url: str,
        kind: str,
        tags: list[str] | None,
        created_by: str | None,
    ) -> dict:
        normalized_url = MediaLibraryService._validate_remote_image_url(url)
        try:
            content, filename = await MediaLibraryService._download_remote_image(normalized_url)
        except httpx.HTTPStatusError as exc:
            raise ValueError(f"Remote image returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise ValueError("Remote image could not be downloaded") from exc
        return await MediaLibraryService.upload_assets(
            session=session,
            files=[(filename, content)],
            kind=kind,
            tags=tags,
            created_by=created_by,
        )

    @staticmethod
    async def backfill_referenced_assets(
        session: AsyncSession,
        *,
        execute: bool = False,
        limit: int = 500,
        include_remote: bool = False,
        created_by: str | None = None,
    ) -> dict:
        safe_limit = max(1, min(int(limit or 500), 5000))
        references = await MediaLibraryService._collect_existing_media_references(session)
        grouped = MediaLibraryService._group_references_by_url(references)

        planned: list[dict] = []
        skipped: list[dict] = []
        created: list[MediaAsset] = []
        errors: list[dict] = []

        for url, refs in grouped.items():
            if len(planned) >= safe_limit:
                break

            existing = await session.scalar(select(MediaAsset).where(MediaAsset.url == url).limit(1))
            if existing:
                skipped.append({"url": url, "reason": "already_indexed"})
                continue

            metadata = MediaLibraryService._metadata_for_existing_reference(
                url,
                include_remote=include_remote,
            )
            if metadata["status"] != "ready":
                skipped.append(
                    {
                        "url": url,
                        "reason": metadata["status"],
                        "path": metadata.get("path"),
                    }
                )
                continue

            primary = refs[0]
            tags = MediaLibraryService._normalize_tags(
                [tag for ref in refs for tag in ref.tags]
            )
            item = {
                "url": url,
                "kind": MediaLibraryService._normalize_kind(primary.kind),
                "title": primary.title,
                "variant_type": primary.variant_type,
                "tags": tags,
                "mime_type": metadata["mime_type"],
                "storage_provider": metadata["storage_provider"],
                "content_hash": metadata["content_hash"],
                "width": metadata["width"],
                "height": metadata["height"],
                "size_bytes": metadata["size_bytes"],
                "references": len(refs),
            }
            planned.append(item)

            if not execute:
                continue

            try:
                asset = MediaAsset(
                    title=item["title"],
                    alt_text=item["title"],
                    kind=item["kind"],
                    tags=item["tags"],
                    variant_type=item["variant_type"],
                    url=url,
                    original_url=url,
                    source_filename=MediaLibraryService._filename_from_url(url),
                    mime_type=item["mime_type"],
                    storage_provider=item["storage_provider"],
                    processing_status="ready",
                    content_hash=item["content_hash"],
                    width=item["width"],
                    height=item["height"],
                    size_bytes=item["size_bytes"],
                    created_by=created_by,
                )
                session.add(asset)
                created.append(asset)
            except Exception as exc:
                errors.append({"url": url, "error": str(exc)})

        if execute and created:
            await session.commit()
            for asset in created:
                await session.refresh(asset)

        return {
            "dry_run": not execute,
            "include_remote": include_remote,
            "limit": safe_limit,
            "references_seen": len(references),
            "unique_urls_seen": len(grouped),
            "planned": len(planned),
            "created": len(created),
            "skipped_count": len(skipped),
            "items": [
                {**item, "id": created[index].id if execute and index < len(created) else None}
                for index, item in enumerate(planned)
            ],
            "skipped": skipped[:100],
            "errors": errors,
        }

    @staticmethod
    async def update_asset(
        session: AsyncSession,
        *,
        asset_id: int,
        title: str | None = None,
        alt_text: str | None = None,
        description: str | None = None,
        kind: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        asset = await session.get(MediaAsset, asset_id)
        if not asset:
            raise LookupError("Media asset not found")

        if title is not None:
            asset.title = title.strip()
        if alt_text is not None:
            asset.alt_text = alt_text.strip() or None
        if description is not None:
            asset.description = description.strip() or None
        if kind is not None:
            asset.kind = MediaLibraryService._normalize_kind(kind)
        if tags is not None:
            asset.tags = MediaLibraryService._normalize_tags(tags)
        asset.updated_at = datetime.now()
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return await MediaLibraryService.serialize_asset(session, asset)

    @staticmethod
    async def crop_asset(
        session: AsyncSession,
        *,
        asset_id: int,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str | None,
        created_by: str | None,
    ) -> dict:
        source = await MediaLibraryService._get_asset_or_raise(session, asset_id)
        if source.mime_type == SVG_MIME_TYPE:
            raise ValueError("SVG assets cannot be cropped")
        source_content = await MediaLibraryService._asset_content_for_processing(source)

        def crop() -> bytes:
            image = MediaLibraryService._open_image(source_content)
            left = max(0, min(x, image.width - 1))
            top = max(0, min(y, image.height - 1))
            right = max(left + 1, min(left + width, image.width))
            bottom = max(top + 1, min(top + height, image.height))
            cropped = image.crop((left, top, right, bottom))
            return MediaLibraryService._export_webp(cropped)

        content = await asyncio.to_thread(crop)
        stored = await MediaLibraryService._store_processed_webp(content, variant_type="crop")
        asset = await MediaLibraryService._create_variant_asset(
            session,
            source=source,
            stored=stored,
            variant_type="crop",
            title=title or f"{source.title or source.source_filename or 'Image'} crop",
            created_by=created_by,
        )
        return await MediaLibraryService.serialize_asset(session, asset)

    @staticmethod
    async def remove_background(
        session: AsyncSession,
        *,
        asset_id: int,
        created_by: str | None,
        provider: str = "auto",
        rembg_model: str | None = None,
    ) -> dict:
        source = await MediaLibraryService._get_asset_or_raise(session, asset_id)
        if source.mime_type == SVG_MIME_TYPE:
            raise ValueError("SVG assets cannot be processed by background removal")
        source_content = await MediaLibraryService._asset_content_for_processing(source)

        processor = get_product_image_processor(provider, rembg_model=rembg_model)
        processed = await processor.process(
            source_content=source_content,
            context=ProductImageProcessingContext(
                product_image_id=0,
                source_url=source.url,
                variant_type=ProductImageVariantType.PROCESSED.value,
            ),
        )
        stored = await MediaLibraryService._store_processed_webp(
            processed.content,
            variant_type="background_removed",
        )
        asset = await MediaLibraryService._create_variant_asset(
            session,
            source=source,
            stored=stored,
            variant_type="background_removed",
            title=f"{source.title or source.source_filename or 'Image'} без фона",
            created_by=created_by,
        )
        return await MediaLibraryService.serialize_asset(session, asset)

    @staticmethod
    async def delete_asset(session: AsyncSession, *, asset_id: int, force: bool = False) -> dict:
        asset = await session.get(MediaAsset, asset_id)
        if not asset:
            raise LookupError("Media asset not found")

        usage_count = await MediaLibraryService._usage_count(session, asset.url)
        if usage_count > 0 and not force:
            raise ValueError("Media asset is used. Pass force=true to delete metadata anyway.")

        url = asset.url
        children = (
            await session.execute(select(MediaAsset).where(MediaAsset.parent_asset_id == asset_id))
        ).scalars().all()
        for child in children:
            child.parent_asset_id = None
            session.add(child)
        await session.delete(asset)
        await session.commit()
        await MediaLibraryService._remove_file_if_unreferenced(session, url)
        return {"message": "Media asset deleted"}

    @staticmethod
    async def serialize_asset(session: AsyncSession, asset: MediaAsset) -> dict:
        return {
            "id": asset.id,
            "parent_asset_id": asset.parent_asset_id,
            "title": asset.title,
            "alt_text": asset.alt_text,
            "description": asset.description,
            "kind": asset.kind,
            "tags": asset.tags or [],
            "variant_type": asset.variant_type,
            "url": asset.url,
            "original_url": asset.original_url,
            "source_filename": asset.source_filename,
            "mime_type": asset.mime_type,
            "storage_provider": asset.storage_provider,
            "processing_status": asset.processing_status,
            "processing_error": asset.processing_error,
            "content_hash": asset.content_hash,
            "width": asset.width,
            "height": asset.height,
            "size_bytes": asset.size_bytes,
            "usage_count": await MediaLibraryService._usage_count(session, asset.url),
            "created_by": asset.created_by,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at,
        }

    @staticmethod
    async def _create_variant_asset(
        session: AsyncSession,
        *,
        source: MediaAsset,
        stored: StoredLibraryImage,
        variant_type: str,
        title: str,
        created_by: str | None,
    ) -> MediaAsset:
        asset = MediaAsset(
            parent_asset_id=source.id,
            title=title,
            alt_text=source.alt_text,
            description=source.description,
            kind=source.kind,
            tags=list(source.tags or []),
            variant_type=variant_type,
            url=stored.url,
            original_url=source.original_url or source.url,
            source_filename=source.source_filename,
            mime_type=stored.mime_type,
            storage_provider=stored.storage_provider,
            processing_status="ready",
            content_hash=stored.content_hash,
            width=stored.width,
            height=stored.height,
            size_bytes=stored.size_bytes,
            created_by=created_by,
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return asset

    @staticmethod
    async def _get_asset_or_raise(session: AsyncSession, asset_id: int) -> MediaAsset:
        asset = await session.get(MediaAsset, asset_id)
        if not asset:
            raise LookupError("Media asset not found")
        return asset

    @staticmethod
    async def _store_image(content: bytes, *, variant_type: str) -> StoredLibraryImage:
        if MediaLibraryService._looks_like_svg(content):
            return await MediaLibraryService._store_svg(content, variant_type=variant_type)

        webp_content = await asyncio.to_thread(
            lambda: MediaLibraryService._export_webp(MediaLibraryService._open_image(content))
        )
        return await MediaLibraryService._store_processed_webp(webp_content, variant_type=variant_type)

    @staticmethod
    async def _download_remote_image(url: str) -> tuple[bytes, str]:
        current_url = url
        async with httpx.AsyncClient(timeout=REMOTE_IMAGE_TIMEOUT_SECONDS, follow_redirects=False) as client:
            for _ in range(4):
                MediaLibraryService._validate_remote_image_url(current_url)
                async with client.stream("GET", current_url, headers={"Accept": "image/*"}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location")
                        if not location:
                            raise ValueError("Remote image redirect has no destination")
                        current_url = str(response.url.join(location))
                        continue

                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if content_type and not content_type.startswith("image/"):
                        raise ValueError("Remote URL does not point to an image")

                    length = response.headers.get("content-length")
                    if length and int(length) > MAX_REMOTE_IMAGE_BYTES:
                        raise ValueError("Remote image is too large")

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_REMOTE_IMAGE_BYTES:
                            raise ValueError("Remote image is too large")
                        chunks.append(chunk)

                    content = b"".join(chunks)
                    if not content:
                        raise ValueError("Remote image is empty")
                    filename = MediaLibraryService._filename_from_url(str(response.url))
                    return content, filename

        raise ValueError("Remote image has too many redirects")

    @staticmethod
    def _validate_remote_image_url(url: str) -> str:
        normalized = str(url or "").strip()
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Image URL must use http or https")

        hostname = parsed.hostname.lower()
        if hostname in {"localhost", "localhost.localdomain"}:
            raise ValueError("Localhost URLs are not allowed")

        try:
            addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise ValueError("Image URL host cannot be resolved") from exc

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError("Private network image URLs are not allowed")
        return normalized

    @staticmethod
    def _filename_from_url(url: str) -> str:
        path = unquote(urlparse(url).path or "")
        filename = Path(path).name.strip()
        return filename or "remote-image"

    @staticmethod
    async def _asset_content_for_processing(asset: MediaAsset) -> bytes:
        source_path = MediaLibraryService._local_path_for_url(asset.url)
        if source_path is not None and source_path.exists():
            return source_path.read_bytes()

        parsed = urlparse(str(asset.url or ""))
        if parsed.scheme in {"http", "https"}:
            content, _ = await MediaLibraryService._download_remote_image(asset.url)
            return content

        raise ValueError("Source file is not available in media storage")

    @staticmethod
    def _general_media_provider() -> str:
        return (os.getenv("MEDIA_STORAGE_PROVIDER", "local") or "local").strip().lower()

    @staticmethod
    async def _store_processed_webp(content: bytes, *, variant_type: str) -> StoredLibraryImage:
        if not content:
            raise ValueError("Cannot store empty media content")

        width, height = await asyncio.to_thread(MediaLibraryService._image_size, content)
        content_hash = hashlib.sha256(content).hexdigest()
        safe_variant = MediaLibraryService._safe_path_segment(variant_type)
        if MediaLibraryService._general_media_provider() != "local":
            stored = await get_general_media_storage().save_media(
                content=content,
                namespace="library",
                variant_type=safe_variant,
                extension="webp",
                content_type="image/webp",
            )
            return StoredLibraryImage(
                url=stored.url,
                path=stored.path,
                content_hash=stored.content_hash,
                width=width,
                height=height,
                size_bytes=stored.size_bytes,
                storage_provider=stored.storage_provider,
            )

        target_dir = MEDIA_LIBRARY_BASE_DIR / safe_variant
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{content_hash}.webp"
        if not target_path.exists():
            target_path.write_bytes(content)

        relative_path = str(target_path).replace(os.sep, "/")
        return StoredLibraryImage(
            url=f"{MEDIA_LIBRARY_PUBLIC_PREFIX}/{safe_variant}/{target_path.name}",
            path=relative_path,
            content_hash=content_hash,
            width=width,
            height=height,
            size_bytes=len(content),
        )

    @staticmethod
    async def _store_svg(content: bytes, *, variant_type: str) -> StoredLibraryImage:
        sanitized, width, height = await asyncio.to_thread(MediaLibraryService._sanitize_svg, content)
        content_hash = hashlib.sha256(sanitized).hexdigest()
        safe_variant = MediaLibraryService._safe_path_segment(variant_type)
        if MediaLibraryService._general_media_provider() != "local":
            stored = await get_general_media_storage().save_media(
                content=sanitized,
                namespace="library",
                variant_type=safe_variant,
                extension="svg",
                content_type=SVG_MIME_TYPE,
            )
            return StoredLibraryImage(
                url=stored.url,
                path=stored.path,
                content_hash=stored.content_hash,
                width=width,
                height=height,
                size_bytes=stored.size_bytes,
                mime_type=SVG_MIME_TYPE,
                storage_provider=stored.storage_provider,
            )

        target_dir = MEDIA_LIBRARY_BASE_DIR / safe_variant
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{content_hash}.svg"
        if not target_path.exists():
            target_path.write_bytes(sanitized)

        relative_path = str(target_path).replace(os.sep, "/")
        return StoredLibraryImage(
            url=f"{MEDIA_LIBRARY_PUBLIC_PREFIX}/{safe_variant}/{target_path.name}",
            path=relative_path,
            content_hash=content_hash,
            width=width,
            height=height,
            size_bytes=len(sanitized),
            mime_type=SVG_MIME_TYPE,
        )

    @staticmethod
    def _open_image(content: bytes) -> Image.Image:
        if not content:
            raise ValueError("Source image is empty")
        try:
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > MAX_LIBRARY_IMAGE_PIXELS:
                    raise ValueError("Source image is too large for safe processing")
                transposed = ImageOps.exif_transpose(image)
                mode = "RGBA" if MediaLibraryService._has_alpha(transposed) else "RGB"
                converted = transposed.convert(mode)
                converted.load()
                return converted.copy()
        except UnidentifiedImageError as exc:
            raise ValueError("Source image cannot be opened") from exc

    @staticmethod
    def _export_webp(image: Image.Image) -> bytes:
        if not features.check("webp"):
            raise RuntimeError("Pillow WebP support is required for media library")
        output = BytesIO()
        image.save(output, format="WEBP", quality=88, method=6, exact=image.mode == "RGBA")
        return output.getvalue()

    @staticmethod
    def _image_size(content: bytes) -> tuple[int, int]:
        image = MediaLibraryService._open_image(content)
        return image.width, image.height

    @staticmethod
    def _looks_like_svg(content: bytes) -> bool:
        prefix = content[:512].lstrip()
        lowered = prefix.lower()
        return lowered.startswith(b"<svg") or lowered.startswith(b"<?xml") and b"<svg" in lowered

    @staticmethod
    def _sanitize_svg(content: bytes) -> tuple[bytes, int, int]:
        if not content:
            raise ValueError("Source SVG is empty")
        if len(content) > MAX_REMOTE_IMAGE_BYTES:
            raise ValueError("Source SVG is too large")

        text = content.decode("utf-8-sig").strip()
        lowered = text.lower()
        if "<!doctype" in lowered or "<!entity" in lowered:
            raise ValueError("SVG doctype and entities are not allowed")

        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise ValueError("Source SVG cannot be parsed") from exc

        if MediaLibraryService._local_xml_name(root.tag) != "svg":
            raise ValueError("Source SVG must have an svg root element")

        for element in root.iter():
            tag_name = MediaLibraryService._local_xml_name(element.tag)
            if tag_name.lower() in SVG_FORBIDDEN_TAGS:
                raise ValueError("SVG contains unsupported embedded content")
            for attr_name, attr_value in element.attrib.items():
                local_attr = MediaLibraryService._local_xml_name(attr_name).lower()
                value = str(attr_value or "").strip().lower()
                if local_attr.startswith("on"):
                    raise ValueError("SVG event handlers are not allowed")
                if local_attr in {"href", "src"} and value and not value.startswith("#"):
                    raise ValueError("SVG external references are not allowed")
                if local_attr == "style" and ("javascript:" in value or "expression(" in value):
                    raise ValueError("SVG unsafe inline styles are not allowed")
                if MediaLibraryService._has_external_svg_url(value):
                    raise ValueError("SVG external references are not allowed")

        width, height = MediaLibraryService._svg_size(root)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True), width, height

    @staticmethod
    def _local_xml_name(name: str) -> str:
        return name.rsplit("}", 1)[-1] if "}" in name else name

    @staticmethod
    def _has_external_svg_url(value: str) -> bool:
        for match in re.finditer(r"url\(([^)]+)\)", value, flags=re.IGNORECASE):
            target = match.group(1).strip(" \t\r\n'\"")
            if target and not target.startswith("#"):
                return True
        return False

    @staticmethod
    def _svg_size(root: ET.Element) -> tuple[int, int]:
        width = MediaLibraryService._svg_dimension(root.attrib.get("width"))
        height = MediaLibraryService._svg_dimension(root.attrib.get("height"))
        if width and height:
            return width, height

        view_box = root.attrib.get("viewBox") or root.attrib.get("viewbox")
        if view_box:
            try:
                parts = [float(part) for part in re.split(r"[\s,]+", view_box.strip()) if part]
            except ValueError:
                parts = []
            if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
                return max(1, round(parts[2])), max(1, round(parts[3]))

        return width or 0, height or 0

    @staticmethod
    def _svg_dimension(value: str | None) -> int:
        if not value:
            return 0
        match = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)", value)
        if not match:
            return 0
        return max(1, round(float(match.group(1))))

    @staticmethod
    def _has_alpha(image: Image.Image) -> bool:
        return image.mode in {"RGBA", "LA"} or (
            image.mode == "P" and "transparency" in image.info
        )

    @staticmethod
    def _local_path_for_url(url: str) -> Path | None:
        if not url:
            return None
        prefix = MEDIA_LIBRARY_PUBLIC_PREFIX.rstrip("/") + "/"
        if url.startswith(prefix):
            relative = url[len(prefix) :]
            return MEDIA_LIBRARY_BASE_DIR / relative
        if url.startswith("/media/"):
            return Path(url.lstrip("/"))
        if url.startswith("media/"):
            return Path(url)
        return None

    @staticmethod
    async def _usage_count(session: AsyncSession, url: str) -> int:
        counts = []
        counts.append(
            await session.scalar(select(func.count()).select_from(Product).where(Product.main_image == url))
        )
        counts.append(
            await session.scalar(select(func.count()).select_from(ProductImage).where(ProductImage.url == url))
        )
        counts.append(
            await session.scalar(
                select(func.count()).select_from(ProductImageVariant).where(ProductImageVariant.url == url)
            )
        )
        counts.append(
            await session.scalar(
                select(func.count()).select_from(Article).where(
                    or_(Article.main_image == url, Article.cover_image == url)
                )
            )
        )
        counts.append(
            await session.scalar(select(func.count()).select_from(Brand).where(Brand.logo_url == url))
        )
        counts.append(
            await session.scalar(
                select(func.count()).select_from(ProductSeries).where(ProductSeries.hero_image == url)
            )
        )
        counts.append(await MediaLibraryService._series_json_usage_count(session, url))
        counts.append(
            await session.scalar(select(func.count()).select_from(ProductAttachment).where(ProductAttachment.url == url))
        )
        counts.append(
            await session.scalar(select(func.count()).select_from(Service).where(Service.image == url))
        )
        return sum(int(value or 0) for value in counts)

    @staticmethod
    async def _collect_existing_media_references(session: AsyncSession) -> list[ExistingMediaReference]:
        references: list[ExistingMediaReference] = []

        products = (await session.execute(select(Product))).scalars().all()
        for product in products:
            title = product.title or f"Product #{product.id}"
            if product.main_image:
                references.append(
                    ExistingMediaReference(
                        url=product.main_image,
                        kind="product",
                        title=title,
                        variant_type="original",
                        tags=("legacy", "product", "main_image"),
                    )
                )
            for image_url in product.images or []:
                if image_url:
                    references.append(
                        ExistingMediaReference(
                            url=str(image_url),
                            kind="product",
                            title=title,
                            variant_type="original",
                            tags=("legacy", "product", "images"),
                        )
                    )

        product_images = (await session.execute(select(ProductImage))).scalars().all()
        for image in product_images:
            references.append(
                ExistingMediaReference(
                    url=image.url,
                    kind="installation" if image.is_installation_photo else "product",
                    title=f"Product image #{image.id}",
                    variant_type="original",
                    tags=("legacy", "product", "gallery"),
                )
            )

        variants = (
            await session.execute(select(ProductImageVariant).where(ProductImageVariant.url.is_not(None)))
        ).scalars().all()
        for variant in variants:
            if not variant.url:
                continue
            references.append(
                ExistingMediaReference(
                    url=variant.url,
                    kind="product",
                    title=f"Product image variant #{variant.id}",
                    variant_type=variant.variant_type,
                    tags=("legacy", "product", "variant", variant.variant_type),
                )
            )

        attachments = (await session.execute(select(ProductAttachment))).scalars().all()
        for attachment in attachments:
            references.append(
                ExistingMediaReference(
                    url=attachment.url,
                    kind="product",
                    title=attachment.title or f"Product attachment #{attachment.id}",
                    variant_type="attachment",
                    tags=("legacy", "product", "attachment", attachment.kind),
                )
            )

        articles = (await session.execute(select(Article))).scalars().all()
        for article in articles:
            title = article.title or f"Article #{article.id}"
            if article.main_image:
                references.append(
                    ExistingMediaReference(
                        url=article.main_image,
                        kind="article",
                        title=title,
                        variant_type="original",
                        tags=("legacy", "article", "main_image"),
                    )
                )
            if article.cover_image:
                references.append(
                    ExistingMediaReference(
                        url=article.cover_image,
                        kind="article",
                        title=title,
                        variant_type="cover",
                        tags=("legacy", "article", "cover_image"),
                    )
                )

        brands = (await session.execute(select(Brand).where(Brand.logo_url.is_not(None)))).scalars().all()
        for brand in brands:
            if not brand.logo_url:
                continue
            references.append(
                ExistingMediaReference(
                    url=brand.logo_url,
                    kind="brand",
                    title=brand.title or f"Brand #{brand.id}",
                    variant_type="logo",
                    tags=("legacy", "brand", "logo"),
                )
            )

        series_rows = (await session.execute(select(ProductSeries))).scalars().all()
        for series in series_rows:
            if series.hero_image:
                references.append(
                    ExistingMediaReference(
                        url=series.hero_image,
                        kind="brand",
                        title=series.title or f"Product series #{series.id}",
                        variant_type="hero",
                        tags=("legacy", "series", "hero"),
                    )
                )
            for image_url in series.gallery_images or []:
                if not image_url:
                    continue
                references.append(
                    ExistingMediaReference(
                        url=str(image_url),
                        kind="brand",
                        title=series.title or f"Product series #{series.id}",
                        variant_type="gallery",
                        tags=("legacy", "series", "gallery"),
                    )
                )
            for block in series.feature_blocks or []:
                if not isinstance(block, dict):
                    continue
                image_url = str(block.get("image_url") or "").strip()
                if not image_url:
                    continue
                references.append(
                    ExistingMediaReference(
                        url=image_url,
                        kind="brand",
                        title=block.get("title") or series.title or f"Product series #{series.id}",
                        variant_type="feature",
                        tags=("legacy", "series", "feature"),
                    )
                )

        services = (await session.execute(select(Service).where(Service.image.is_not(None)))).scalars().all()
        for service in services:
            if not service.image:
                continue
            references.append(
                ExistingMediaReference(
                    url=service.image,
                    kind="service",
                    title=service.title or f"Service #{service.id}",
                    variant_type="original",
                    tags=("legacy", "service"),
                )
            )

        return [ref for ref in references if ref.url]

    @staticmethod
    async def _series_json_usage_count(session: AsyncSession, url: str) -> int:
        if not url:
            return 0

        count = 0
        series_rows = (await session.execute(select(ProductSeries))).scalars().all()
        for series in series_rows:
            count += sum(1 for image_url in series.gallery_images or [] if image_url == url)
            for block in series.feature_blocks or []:
                if isinstance(block, dict) and block.get("image_url") == url:
                    count += 1
        return count

    @staticmethod
    def _group_references_by_url(
        references: list[ExistingMediaReference],
    ) -> dict[str, list[ExistingMediaReference]]:
        grouped: dict[str, list[ExistingMediaReference]] = {}
        for ref in references:
            url = str(ref.url or "").strip()
            if not url:
                continue
            grouped.setdefault(url, []).append(ref)
        return grouped

    @staticmethod
    def _metadata_for_existing_reference(url: str, *, include_remote: bool) -> dict:
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            if not include_remote:
                return {"status": "remote_skipped"}
            return {
                "status": "ready",
                "mime_type": MediaLibraryService._guess_mime_type(url),
                "storage_provider": "remote",
                "content_hash": None,
                "width": None,
                "height": None,
                "size_bytes": 0,
                "path": None,
            }

        path = MediaLibraryService._local_path_for_url(url)
        if path is None:
            return {"status": "unsupported_url"}
        if not path.exists():
            return {"status": "missing_file", "path": str(path)}

        try:
            content = path.read_bytes()
            if MediaLibraryService._looks_like_svg(content):
                _, width, height = MediaLibraryService._sanitize_svg(content)
                mime_type = SVG_MIME_TYPE
            else:
                width, height = MediaLibraryService._image_size(content)
                mime_type = MediaLibraryService._guess_mime_type(str(path))

            return {
                "status": "ready",
                "mime_type": mime_type,
                "storage_provider": "local",
                "content_hash": hashlib.sha256(content).hexdigest(),
                "width": width or None,
                "height": height or None,
                "size_bytes": len(content),
                "path": str(path),
            }
        except Exception as exc:
            return {"status": "metadata_error", "path": str(path), "error": str(exc)}

    @staticmethod
    async def _remove_file_if_unreferenced(session: AsyncSession, url: str) -> None:
        media_refs = await session.scalar(
            select(func.count()).select_from(MediaAsset).where(MediaAsset.url == url)
        )
        if int(media_refs or 0) > 0:
            return
        if await MediaLibraryService._usage_count(session, url) > 0:
            return
        path = MediaLibraryService._local_path_for_url(url)
        if path and path.exists():
            path.unlink()

    @staticmethod
    def _normalize_kind(kind: str | None) -> str:
        normalized = (kind or "misc").strip().lower().replace(" ", "_")
        return normalized if normalized in ALLOWED_KINDS else "misc"

    @staticmethod
    def _normalize_tags(tags: list[str] | None) -> list[str]:
        result = []
        seen = set()
        for tag in tags or []:
            normalized = MediaLibraryService._normalize_tag(tag)
            if not normalized or normalized.casefold() in seen:
                continue
            seen.add(normalized.casefold())
            result.append(normalized)
        return result

    @staticmethod
    def _normalize_tag(tag: str | None) -> str:
        return " ".join(str(tag or "").strip().split())

    @staticmethod
    def _title_from_filename(filename: str | None) -> str:
        if not filename:
            return ""
        return Path(filename).stem.replace("_", " ").replace("-", " ").strip()

    @staticmethod
    def _safe_path_segment(value: str) -> str:
        safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
        return safe.strip("_") or "misc"

    @staticmethod
    def _guess_mime_type(value: str) -> str:
        guessed, _ = mimetypes.guess_type(value)
        return guessed or "application/octet-stream"
