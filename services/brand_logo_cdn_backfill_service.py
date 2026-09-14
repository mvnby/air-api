"""Plan and atomically migrate the reviewed legacy brand logos to the CDN."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models import Brand, MediaAsset
from services.catalog_media_policy import CatalogMediaKind, CatalogMediaPolicy
from services.catalog_mutation_contracts import require_global_catalog_mutation_contract
from services.catalog_revision_service import CatalogRevisionService
from services.general_media_storage_service import (
    GeneralMediaStorage,
    get_general_media_storage,
)
from services.media_library_service import MediaLibraryService, SVG_MIME_TYPE
from services.product_media_url_backfill_plan_token import (
    ProductMediaUrlBackfillBlockedError,
    ProductMediaUrlBackfillPlanToken,
)


MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
TIMEOUT_SECONDS = 15.0
ALLOWED_CONTENT_TYPES = {"image/png", "image/svg+xml"}


@dataclass(frozen=True, slots=True)
class BrandLogoRule:
    brand_id: int
    title: str
    slug: str
    old_url: str
    allowed_hosts: tuple[str, ...]
    source_content_hash: str
    target_content_hash: str
    extension: str
    width: int
    height: int


RULES = (
    BrandLogoRule(
        2,
        "Chigo",
        "chigo",
        "https://mvn.by/img/logos/chigo.svg",
        ("mvn.by",),
        "400ca0a7e70600533edafd3abde69254e8362e9ed4e6afc4acae038be54bc318",
        "867ef8cbc9abafb625584019d5efea46280a57d13da40c24c8c83ca5ec51d26b",
        "svg",
        1176,
        262,
    ),
    BrandLogoRule(
        13,
        "Ultima Comfort",
        "ultima",
        "https://ultimacomfort.ru/images/logo.svg",
        ("ultimacomfort.ru",),
        "b210cfe0bfb651ac7c610a0c6b1383d45b524fbc14551c6cf23173217454f205",
        "dff2bc5923a1ad551e8bc65dc4431dab654d1576ce2af3937df38c1d031495e1",
        "svg",
        158,
        48,
    ),
    BrandLogoRule(
        50,
        "Gree",
        "gree",
        "https://upload.wikimedia.org/wikipedia/commons/0/01/Gree_electric_appliances_logo.svg",
        ("upload.wikimedia.org",),
        "7456c88e927b185dc57bb14d4abff9ff88430aa0674a10c0761d5debd5b413da",
        "bf403fb3a043559ea02d7d2bb5b6c76130bd44782eea3b75575be61838116510",
        "svg",
        2500,
        510,
    ),
    BrandLogoRule(
        14,
        "Mitsubishi Heavy",
        "mitsubishi-heavy",
        "https://mhi-aircond.ru/images/svg/mhi_logo.svg",
        ("mhi-aircond.ru",),
        "fc0cab195c3dfaa73212d253aacd7cd77702f97128198a5718ad2e4b458809fc",
        "68e7156320bccf4e7f6d49833379a0e9dac57b02027dc0358e73c44c87afeb78",
        "svg",
        138,
        30,
    ),
    BrandLogoRule(
        51,
        "Daikin",
        "daikin",
        "https://upload.wikimedia.org/wikipedia/commons/0/05/DAIKIN_logo.svg",
        ("upload.wikimedia.org",),
        "57436b9db7568e1c3d411b021f488eb18c47ec6cba0cc6807ae58cebc5f7a66b",
        "8d54be21475ee67df63c5fae1aaf7b81f385edbf2bc8a74ec9f87bb64aed5387",
        "svg",
        300,
        65,
    ),
    BrandLogoRule(
        12,
        "Energolux",
        "energolux",
        "https://www.severcon.ru/upload/medialibrary/56d/LOGO_170.png",
        ("www.severcon.ru",),
        "51b7f9dd2d87c130bd32e85b3b40993d2d3bc05cbc912c057c7a78d6bd213ecc",
        "f6d489a745685420618e5d951f7118db18ba5545550977d21c576d357d166473",
        "webp",
        170,
        39,
    ),
)


@dataclass(frozen=True, slots=True)
class DownloadedLogo:
    content: bytes
    content_type: str
    content_hash: str
    final_url: str


class BrandLogoBackfillBlockedError(ProductMediaUrlBackfillBlockedError):
    pass


class BrandLogoDownloader:
    def __init__(self, *, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def download(self, rule: BrandLogoRule) -> DownloadedLogo:
        current = rule.old_url
        allowed_hosts = {host.lower() for host in rule.allowed_hosts}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_SECONDS),
            follow_redirects=False,
            headers={
                "Accept": "image/svg+xml,image/png",
                "User-Agent": "MVN reviewed brand-logo backfill/1 (https://mvn.by/)",
            },
        )
        try:
            for redirect_count in range(MAX_REDIRECTS + 1):
                await self._validate_url(current, allowed_hosts)
                async with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count >= MAX_REDIRECTS:
                            raise BrandLogoBackfillBlockedError(
                                "Logo redirect chain is invalid"
                            )
                        current = urljoin(current, location)
                        continue
                    if response.status_code != 200:
                        raise BrandLogoBackfillBlockedError(
                            f"Logo source returned HTTP {response.status_code}"
                        )
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .lower()
                    )
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        raise BrandLogoBackfillBlockedError(
                            "Logo content type is not allowed"
                        )
                    declared = response.headers.get("content-length")
                    if declared and (
                        int(declared) < 1 or int(declared) > MAX_LOGO_BYTES
                    ):
                        raise BrandLogoBackfillBlockedError(
                            "Logo exceeds the 2 MiB limit"
                        )
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_LOGO_BYTES:
                            raise BrandLogoBackfillBlockedError(
                                "Logo exceeds the 2 MiB limit"
                            )
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    if not content:
                        raise BrandLogoBackfillBlockedError("Logo source is empty")
                    return DownloadedLogo(
                        content=content,
                        content_type=content_type,
                        content_hash=hashlib.sha256(content).hexdigest(),
                        final_url=str(response.url),
                    )
            raise BrandLogoBackfillBlockedError("Logo redirect chain is too long")
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, BrandLogoBackfillBlockedError):
                raise
            raise BrandLogoBackfillBlockedError("Logo download failed") from exc
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
            raise BrandLogoBackfillBlockedError(
                "Logo URL is outside the reviewed boundary"
            )
        try:
            addresses = await asyncio.to_thread(cls._resolve_addresses, hostname)
        except OSError as exc:
            raise BrandLogoBackfillBlockedError("Logo host DNS lookup failed") from exc
        if not addresses or any(
            not ipaddress.ip_address(item).is_global for item in addresses
        ):
            raise BrandLogoBackfillBlockedError(
                "Logo host did not resolve to public addresses"
            )

    @staticmethod
    def _resolve_addresses(hostname: str) -> set[str]:
        return {
            str(item[4][0])
            for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        }


class BrandLogoCdnBackfillService:
    LOCK_NAME = "mvn:brand-logo-cdn-backfill:v1"
    RIGHTS_REVIEW_REF = "user-approved-existing-publication-migration-2026-09-14"

    @classmethod
    async def plan(
        cls,
        session: AsyncSession,
        *,
        downloader: BrandLogoDownloader | None = None,
        storage: GeneralMediaStorage | None = None,
        issue_token: bool = True,
    ) -> dict[str, object]:
        active_storage = storage or get_general_media_storage(require_write=False)
        brands = list(
            (
                await session.execute(
                    select(Brand).where(Brand.is_published.is_(True)).order_by(Brand.id)
                )
            ).scalars()
        )
        brands_by_id = {
            int(brand.id): brand for brand in brands if brand.id is not None
        }
        expected_ids = {rule.brand_id for rule in RULES}
        unexpected = [
            {"brand_id": int(brand.id), "slug": brand.slug, "logo_url": brand.logo_url}
            for brand in brands
            if brand.logo_url
            and not CatalogMediaPolicy.is_allowed_cdn(
                brand.logo_url, kind=CatalogMediaKind.CONTENT
            )
            and int(brand.id) not in expected_ids
        ]
        blockers: list[str] = []
        if unexpected:
            blockers.append("Published catalog contains unreviewed non-CDN brand logos")

        evidence: list[dict[str, object]] = []
        changes: list[dict[str, object]] = []
        active_downloader = downloader or BrandLogoDownloader()
        for rule in RULES:
            target = active_storage.build_media_object(
                content_hash=rule.target_content_hash,
                namespace="library",
                variant_type="original",
                extension=rule.extension,
            )
            brand = brands_by_id.get(rule.brand_id)
            if brand is None or brand.title != rule.title or brand.slug != rule.slug:
                blockers.append(f"Brand identity drifted for id={rule.brand_id}")
                continue
            if brand.logo_url == target.url:
                evidence.append(cls._evidence(rule, target.url, status="complete"))
                continue
            if brand.logo_url != rule.old_url:
                blockers.append(f"Brand logo drifted for id={rule.brand_id}")
                evidence.append(cls._evidence(rule, target.url, status="drifted"))
                continue
            try:
                downloaded = await active_downloader.download(rule)
                processed, extension, width, height = await cls._process(
                    downloaded.content
                )
                processed_hash = hashlib.sha256(processed).hexdigest()
                if not hmac.compare_digest(
                    downloaded.content_hash, rule.source_content_hash
                ):
                    raise BrandLogoBackfillBlockedError(
                        "Source bytes changed after review"
                    )
                if (
                    extension != rule.extension
                    or width != rule.width
                    or height != rule.height
                    or not hmac.compare_digest(processed_hash, rule.target_content_hash)
                ):
                    raise BrandLogoBackfillBlockedError(
                        "Processed logo differs from review"
                    )
                evidence.append(
                    {
                        **cls._evidence(rule, target.url, status="ready"),
                        "final_url": downloaded.final_url,
                        "source_size_bytes": len(downloaded.content),
                        "target_size_bytes": len(processed),
                    }
                )
                changes.append(
                    {
                        "brand_id": rule.brand_id,
                        "slug": rule.slug,
                        "old_url": rule.old_url,
                        "new_url": target.url,
                    }
                )
            except (BrandLogoBackfillBlockedError, ValueError) as exc:
                blockers.append(f"Brand id={rule.brand_id}: {exc}")
                evidence.append(
                    {
                        **cls._evidence(rule, target.url, status="blocked"),
                        "error": str(exc),
                    }
                )

        payload = {
            "changes": changes,
            "evidence": evidence,
            "unexpected": unexpected,
            "blockers": sorted(set(blockers)),
        }
        plan_digest = hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        ready = not blockers
        result: dict[str, object] = {
            "mode": "plan",
            "ready": ready,
            "complete": ready and not changes,
            "published_brand_count": len(brands),
            "change_count": len(changes),
            "changes": changes,
            "source_evidence": evidence,
            "unreviewed_non_cdn_logos": unexpected,
            "blockers": sorted(set(blockers)),
            "plan_digest": plan_digest,
            "rights_review_ref": cls.RIGHTS_REVIEW_REF,
        }
        if issue_token and ready and changes:
            result["plan_token"] = ProductMediaUrlBackfillPlanToken.issue(
                plan_digest=plan_digest
            )
        return result

    @classmethod
    async def execute(
        cls,
        session: AsyncSession,
        *,
        plan_token: str,
        downloader: BrandLogoDownloader | None = None,
        storage: GeneralMediaStorage | None = None,
    ) -> dict[str, object]:
        verified = ProductMediaUrlBackfillPlanToken.verify(plan_token)
        await cls._require_primary_and_lock(session)
        active_downloader = downloader or BrandLogoDownloader()
        active_storage = storage or get_general_media_storage(require_write=True)
        reviewed = await cls.plan(
            session,
            downloader=active_downloader,
            storage=active_storage,
            issue_token=False,
        )
        if not hmac.compare_digest(str(reviewed["plan_digest"]), verified.plan_digest):
            raise BrandLogoBackfillBlockedError(
                "Brand logo plan is stale; run a fresh plan"
            )
        if not reviewed["ready"]:
            raise BrandLogoBackfillBlockedError("Brand logo plan is blocked")

        changed_slugs: list[str] = []
        rules_by_id = {rule.brand_id: rule for rule in RULES}
        for item in reviewed["changes"]:
            rule = rules_by_id[int(item["brand_id"])]
            brand = await session.get(Brand, rule.brand_id, with_for_update=True)
            if brand is None or brand.logo_url != rule.old_url:
                raise BrandLogoBackfillBlockedError(
                    f"Brand logo drifted for id={rule.brand_id}"
                )
            downloaded = await active_downloader.download(rule)
            if not hmac.compare_digest(
                downloaded.content_hash, rule.source_content_hash
            ):
                raise BrandLogoBackfillBlockedError(
                    "Logo source changed after the reviewed plan"
                )
            processed, extension, width, height = await cls._process(downloaded.content)
            if (
                extension != rule.extension
                or width != rule.width
                or height != rule.height
                or not hmac.compare_digest(
                    hashlib.sha256(processed).hexdigest(), rule.target_content_hash
                )
            ):
                raise BrandLogoBackfillBlockedError(
                    "Processed logo changed after the reviewed plan"
                )
            stored = await active_storage.save_media(
                content=processed,
                namespace="library",
                variant_type="original",
                extension=extension,
                content_type=SVG_MIME_TYPE if extension == "svg" else "image/webp",
            )
            if stored.url != item["new_url"] or not CatalogMediaPolicy.is_allowed_cdn(
                stored.url, kind=CatalogMediaKind.CONTENT
            ):
                raise BrandLogoBackfillBlockedError(
                    "Media storage returned an unexpected logo URL"
                )
            existing_asset = (
                await session.execute(
                    select(MediaAsset).where(MediaAsset.url == stored.url)
                )
            ).scalar_one_or_none()
            if existing_asset is None:
                session.add(
                    MediaAsset(
                        title=f"{rule.title} logo",
                        alt_text=rule.title,
                        kind="brand_logo",
                        tags=["brand", rule.slug],
                        variant_type="original",
                        url=stored.url,
                        original_url=rule.old_url,
                        source_filename=urlsplit(rule.old_url).path.rsplit("/", 1)[-1],
                        mime_type=SVG_MIME_TYPE if extension == "svg" else "image/webp",
                        storage_provider=stored.storage_provider,
                        processing_status="ready",
                        content_hash=stored.content_hash,
                        width=width,
                        height=height,
                        size_bytes=stored.size_bytes,
                        created_by="brand-logo-cdn-backfill",
                    )
                )
            brand.logo_url = stored.url
            session.add(brand)
            changed_slugs.append(rule.slug)

        if changed_slugs:
            contract = require_global_catalog_mutation_contract(
                "brand_logo.cdn_backfill"
            )
            await CatalogRevisionService.stage_invalidation(
                session,
                reason=contract.reason,
                brand_slugs=changed_slugs,
            )
        return {
            "mode": "execute",
            "changed": bool(changed_slugs),
            "changed_brand_count": len(changed_slugs),
            "changed_brand_slugs": changed_slugs,
            "reviewed_plan_digest": reviewed["plan_digest"],
            "requires_post_commit_public_verification": True,
        }

    @staticmethod
    async def _process(content: bytes) -> tuple[bytes, str, int, int]:
        if MediaLibraryService._looks_like_svg(content):
            sanitized, width, height = await asyncio.to_thread(
                MediaLibraryService._sanitize_svg, content
            )
            return sanitized, "svg", width, height
        webp = await asyncio.to_thread(MediaLibraryService._source_to_webp, content)
        width, height = await asyncio.to_thread(MediaLibraryService._image_size, webp)
        return webp, "webp", width, height

    @classmethod
    def _evidence(
        cls, rule: BrandLogoRule, target_url: str, *, status: str
    ) -> dict[str, object]:
        return {
            "brand_id": rule.brand_id,
            "slug": rule.slug,
            "old_url": rule.old_url,
            "target_url": target_url,
            "status": status,
            "source_content_hash": rule.source_content_hash,
            "target_content_hash": rule.target_content_hash,
            "target_width": rule.width,
            "target_height": rule.height,
            "rights_review_ref": cls.RIGHTS_REVIEW_REF,
        }

    @classmethod
    async def _require_primary_and_lock(cls, session: AsyncSession) -> None:
        if session.bind is None or session.bind.dialect.name != "postgresql":
            raise BrandLogoBackfillBlockedError(
                "Execute is supported only on PostgreSQL primary"
            )
        if bool(
            (await session.execute(text("SELECT pg_is_in_recovery()"))).scalar_one()
        ):
            raise BrandLogoBackfillBlockedError(
                "Brand logo backfill cannot run on a standby"
            )
        acquired = bool(
            (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_name))"),
                    {"lock_name": cls.LOCK_NAME},
                )
            ).scalar_one()
        )
        if not acquired:
            raise BrandLogoBackfillBlockedError(
                "Another brand logo backfill owns the lock"
            )


__all__ = [
    "BrandLogoBackfillBlockedError",
    "BrandLogoCdnBackfillService",
    "BrandLogoDownloader",
    "BrandLogoRule",
    "RULES",
]
