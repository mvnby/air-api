"""Publish reviewed library references without editing feature semantics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field


# This rollout is deliberately bounded to the source-reviewed visual inventory.
FEATURE_IDS = frozenset({7, 15, 16, 18, 19, 24, 27, 29, 31, 34, 36, 37, 38,
    39, 40, 41, 73, 77, 78, 79, 80, 84, 85, 86, 87, 120, 121, 122, 123,
    124, 125, 127, 128, 129, 130})
IMAGE_IDS = frozenset({19, 31, 38, 41, 77, 78, 79, 87, 121, 127, 128, 129, 130})
MEDIA_FIELDS = ("icon", "icon_media_id", "image_url", "image_media_id")
WRITE_FIELDS = frozenset({"icon_media_id", "image_media_id", "image_url"})
PLAN_TTL = timedelta(minutes=30)
LOCK_KEY = 63049083715264811


class PublicationBlocked(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FeatureIdentity(StrictModel):
    id: int = Field(gt=0)
    slug: str = Field(min_length=1)
    scope_type: Literal["universal", "brand", "series", "product", "derived"]
    brand_id: int | None


class MediaState(StrictModel):
    icon: str | None
    icon_media_id: int | None
    image_url: str | None
    image_media_id: int | None


class MediaReference(StrictModel):
    id: int = Field(gt=0)
    url: str = Field(min_length=1, max_length=2048)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class MediaTarget(StrictModel):
    icon: MediaReference
    image: MediaReference | None = None


class FeatureMediaRow(StrictModel):
    identity: FeatureIdentity
    before: MediaState
    target: MediaTarget


class PublicationManifest(StrictModel):
    schema_version: Literal[1]
    features: list[FeatureMediaRow] = Field(min_length=35, max_length=35)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_manifest(value: Any) -> dict[str, Any]:
    manifest = PublicationManifest.model_validate(value).model_dump()
    ids = [row["identity"]["id"] for row in manifest["features"]]
    slugs = [row["identity"]["slug"] for row in manifest["features"]]
    if len(set(ids)) != len(ids) or len(set(slugs)) != len(slugs):
        raise PublicationBlocked("Duplicate feature identity in manifest")
    if set(ids) != FEATURE_IDS:
        raise PublicationBlocked("Manifest must contain the exact 35 reviewed feature IDs")
    images = {row["identity"]["id"] for row in manifest["features"] if row["target"]["image"]}
    if images != IMAGE_IDS:
        raise PublicationBlocked("Manifest must contain the exact 13 reviewed illustrations")
    manifest["features"].sort(key=lambda row: row["identity"]["id"])
    return manifest


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PublicationBlocked(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object)


def load_manifest(path: Path) -> dict[str, Any]:
    return validate_manifest(load_json(path))


def _media_reference(ref: dict, assets: dict[int, Any], storage: Any) -> dict:
    asset = assets.get(ref["id"])
    if asset is None:
        raise PublicationBlocked(f"Media asset {ref['id']} is missing")
    actual = {key: getattr(asset, key) for key in ("id", "url", "content_hash")}
    if actual != ref:
        raise PublicationBlocked(f"Media asset {ref['id']} differs from reviewed reference")
    if (asset.kind != "feature" or asset.processing_status != "ready"
        or asset.variant_type != "original" or asset.parent_asset_id is not None
        or asset.tenant_id is not None or asset.storefront_id is not None):
        raise PublicationBlocked(f"Media asset {ref['id']} must be a ready global original feature asset")
    extension = {"image/svg+xml": "svg", "image/webp": "webp"}.get(asset.mime_type)
    if extension is None:
        raise PublicationBlocked(f"Media asset {ref['id']} has unsupported library MIME type")
    if asset.storage_provider == "local":
        canonical_url = f"/media/library/original/{asset.content_hash}.{extension}"
    else:
        canonical_url = storage.build_media_object(content_hash=asset.content_hash,
            namespace="library", variant_type="original", extension=extension).url
        if asset.storage_provider != storage.provider_name:
            raise PublicationBlocked(f"Media asset {ref['id']} storage provider changed")
    if asset.url != canonical_url:
        raise PublicationBlocked(f"Media asset {ref['id']} URL is outside canonical library storage")
    return {**actual, **{key: getattr(asset, key) for key in (
        "kind", "processing_status", "variant_type", "parent_asset_id", "tenant_id",
        "storefront_id", "mime_type", "storage_provider")}}


def build_plan(manifest: dict, features: list, assets: list, *, storage: Any,
    affected_scope: dict, now: datetime | None = None) -> dict:
    """Pure planner: accept exactly the before state or the complete target state."""
    manifest = validate_manifest(manifest)
    feature_map = {row.id: row for row in features}
    if set(feature_map) != FEATURE_IDS or len(features) != len(FEATURE_IDS):
        raise PublicationBlocked("Exact reviewed feature set is unavailable")
    asset_map = {row.id: row for row in assets}
    observed, operations = [], []
    for row in manifest["features"]:
        identity = row["identity"]
        feature = feature_map[identity["id"]]
        if {key: getattr(feature, key) for key in identity} != identity:
            raise PublicationBlocked(f"Feature {feature.id} identity drifted")
        before = row["before"]
        target = {**before, "icon_media_id": row["target"]["icon"]["id"]}
        media = {"icon": _media_reference(row["target"]["icon"], asset_map, storage)}
        if image := row["target"]["image"]:
            target.update(image_media_id=image["id"], image_url=image["url"])
            media["image"] = _media_reference(image, asset_map, storage)
        actual = {key: getattr(feature, key) for key in MEDIA_FIELDS}
        if actual != before and actual != target:
            raise PublicationBlocked(f"Feature {feature.id} media drifted from before/complete target")
        changes = {key: value for key, value in target.items() if actual[key] != value}
        if changes.keys() - WRITE_FIELDS:
            raise PublicationBlocked("Publication attempted a non-media field")
        observed.append({"identity": identity, "before_guard": before, "observed": actual,
            "after_guard": target, "assets": media})
        if changes:
            operations.append({"id": feature.id, "set": changes})
    payload = {"schema_version": 1, "ready": True, "manifest_sha256": digest(manifest),
        "observed": observed, "operations": operations, "changed": len(operations),
        "affected_scope": affected_scope}
    payload["state_digest"] = digest(payload)
    now = now or datetime.now(timezone.utc)
    payload["created_at"] = now.isoformat()
    payload["expires_at"] = (now + PLAN_TTL).isoformat()
    payload["plan_digest"] = digest(payload)
    return payload


def validate_reviewed_plan(reviewed: dict, live: dict, supplied_digest: str,
    *, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    if not isinstance(reviewed, dict):
        raise PublicationBlocked("Reviewed plan must be an object")
    unsigned = {key: value for key, value in reviewed.items() if key != "plan_digest"}
    if reviewed.get("plan_digest") != supplied_digest or digest(unsigned) != supplied_digest:
        raise PublicationBlocked("Reviewed plan digest is invalid")
    reviewed_state = {key: value for key, value in reviewed.items()
        if key not in {"state_digest", "created_at", "expires_at", "plan_digest"}}
    if digest(reviewed_state) != reviewed.get("state_digest"):
        raise PublicationBlocked("Reviewed plan state digest is invalid")
    try:
        created = datetime.fromisoformat(reviewed["created_at"])
        expires = datetime.fromisoformat(reviewed["expires_at"])
        valid = created <= now < expires and expires - created == PLAN_TTL
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise PublicationBlocked("Reviewed plan expired or has an invalid validity window")
    if reviewed.get("state_digest") != live["state_digest"]:
        raise PublicationBlocked("Manifest, media or affected catalog state changed since review")


def require_primary(in_recovery: object) -> None:
    if in_recovery is not False:
        raise PublicationBlocked("Execute requires a positively verified PostgreSQL primary")


async def run(*, manifest_path: Path, execute: bool = False,
    reviewed_plan: Path | None = None, execute_plan_digest: str | None = None) -> dict:
    manifest = load_manifest(manifest_path)
    if execute and (reviewed_plan is None or not execute_plan_digest):
        raise PublicationBlocked("Execute requires --reviewed-plan and --execute-plan-digest")
    if not execute and (reviewed_plan is not None or execute_plan_digest is not None):
        raise PublicationBlocked("Review arguments require --execute")
    reviewed = load_json(reviewed_plan) if execute else None
    # Keep --help/manifest rejection independent of runtime DB configuration.
    from sqlalchemy import text
    from sqlmodel import select
    from core.database import async_session_maker
    from models import Brand, Feature, MediaAsset, Product, ProductSeries
    from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService
    from services.general_media_storage_service import get_general_media_storage

    storage = get_general_media_storage(require_write=False)
    async with async_session_maker() as session:
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
            + ("" if execute else ", READ ONLY")))
        if execute:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            require_primary(await session.scalar(text("SELECT pg_is_in_recovery()")))
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})

        async def locked_rows(model, ids):
            query = select(model).where(model.id.in_(sorted(ids))).order_by(model.id)
            if execute:
                query = query.with_for_update(of=model)
            return list((await session.execute(query)).scalars())

        features = await locked_rows(Feature, FEATURE_IDS)
        media_ids = {ref["id"] for row in manifest["features"]
            for ref in row["target"].values() if ref}
        assets = await locked_rows(MediaAsset, media_ids)
        # Broad, explicit policy: universal features can affect any catalog brand.
        products = (await session.execute(select(Product.id, Product.slug).order_by(Product.id))).all()
        brands = (await session.execute(select(Brand.id, Brand.slug).order_by(Brand.id))).all()
        series = (await session.execute(select(ProductSeries.brand_id, ProductSeries.slug)
            .order_by(ProductSeries.id))).all()
        brand_map = dict(brands)
        affected_scope = {"policy": "full_global_catalog", "feature_ids": sorted(FEATURE_IDS),
            "product_ids": [row.id for row in products],
            "product_slugs": sorted({row.slug for row in products if row.slug}),
            "brand_slugs": sorted({row.slug for row in brands if row.slug}),
            "series_paths": sorted({f"/brands/{quote(brand_map[brand_id], safe='')}/series/{quote(slug, safe='')}/"
                for brand_id, slug in series if brand_map.get(brand_id) and slug})}
        plan = build_plan(manifest, features, assets, storage=storage, affected_scope=affected_scope)
        if not execute:
            await session.rollback()
            return plan
        validate_reviewed_plan(reviewed, plan, execute_plan_digest)
        if not plan["changed"]:
            await session.rollback()
            return {"mode": "execute", "changed": 0, "reviewed_plan_digest": execute_plan_digest, "revision": None}
        feature_map = {row.id: row for row in features}
        for operation in plan["operations"]:
            for field, value in operation["set"].items():
                if field not in WRITE_FIELDS:
                    raise PublicationBlocked("Publication attempted a non-media field")
                setattr(feature_map[operation["id"]], field, value)
        revision = await CatalogInvalidationCommitService.commit_global_mutation(session,
            reason="reviewed_feature_media_publication", product_ids=affected_scope["product_ids"],
            slugs=affected_scope["product_slugs"], brand_slugs=affected_scope["brand_slugs"],
            additional_paths=affected_scope["series_paths"])
        return {"mode": "execute", "changed": plan["changed"],
            "reviewed_plan_digest": execute_plan_digest, "revision": revision}
