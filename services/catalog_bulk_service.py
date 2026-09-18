from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from api_contracts.catalog_bulk import CatalogBulkChange, CatalogBulkPreviewRequest
from crud.product import ProductDAO
from models import Brand, Feature, FeatureProductLink, Product, ProductSeries
from schemas_features import FeatureLinkPayload
from services.catalog_bulk_token import digest, read_preview, sign_preview
from services.feature_assignment_service import FeatureAssignmentService
from services.feature_resolver_service import FeatureResolverService
from services.product_write_service import ProductWriteService
from services.spec_normalizer import KEY_MAP, normalize_specs


class CatalogBulkConflict(ValueError):
    pass


class CatalogBulkService:
    _ASSIGNMENT_FIELDS = (
        "feature_id",
        "source",
        "is_enabled",
        "sort_order",
        "override_title",
        "override_description",
        "override_media_id",
        "override_image_url",
        "override_icon",
        "override_footnote",
    )

    @classmethod
    def _assignment_snapshot(cls, link: FeatureProductLink) -> dict[str, Any]:
        return {field: getattr(link, field) for field in cls._ASSIGNMENT_FIELDS}

    @staticmethod
    def _canonical_spec_key(key: object) -> str:
        raw = str(key).strip()
        if not raw:
            return raw
        normalized = KEY_MAP.get(raw)
        if normalized:
            return normalized
        folded = raw.casefold()
        for alias, canonical_key in KEY_MAP.items():
            if str(alias).strip().casefold() == folded:
                return canonical_key
        return raw

    @classmethod
    def _spec_targets(cls, specs: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
        if any(str(key).startswith("__") for key in specs):
            raise ValueError("Служебные поля характеристик недоступны.")
        if any(cls._canonical_spec_key(key) in {"brand", "series"} for key in specs):
            raise ValueError("Бренд и серия изменяются через действие «Бренд и серия».")
        normalized = normalize_specs(specs)
        baseline = normalize_specs({})
        targets = {cls._canonical_spec_key(key) for key in specs}
        # A composite legacy input can normalize into several public fields.
        # Include only fields changed from the empty normalization baseline, so
        # default wifi state is not accidentally edited with every request.
        targets.update(
            cls._canonical_spec_key(key)
            for key, value in normalized.items()
            if not str(key).startswith("__") and baseline.get(key) != value
        )
        # Empty removal values do not reveal dependent public fields (Wi-Fi
        # expands to ready/builtin/state, for example). Probe each submitted
        # key so removal clears those stale projections before normalization.
        for raw_key in specs:
            probe = normalize_specs({str(raw_key): True})
            targets.update(
                cls._canonical_spec_key(key)
                for key, value in probe.items()
                if not str(key).startswith("__") and baseline.get(key) != value
            )
        if not targets:
            raise ValueError("Не удалось определить характеристики для изменения.")
        return normalized, targets

    @classmethod
    def _specs_after_change(cls, current: dict[str, Any], change: CatalogBulkChange) -> dict[str, Any]:
        normalized, targets = cls._spec_targets(change.specs)
        # Filter and typed entries are derived from user-facing specs. Keeping
        # them here would retain stale values after a delete or alias rewrite.
        result = {
            key: value
            for key, value in dict(current or {}).items()
            if not str(key).startswith("__")
        }
        replaced_targets = {
            target
            for target in targets
            if change.spec_mode != "fill_empty" or not any(
                existing_value not in (None, "")
                for existing_key, existing_value in (current or {}).items()
                if cls._canonical_spec_key(existing_key) == target
            )
        }
        if change.spec_mode == "remove":
            replaced_targets = targets
        result = {
            key: value
            for key, value in result.items()
            if cls._canonical_spec_key(key) not in replaced_targets
        }
        if change.spec_mode != "remove":
            result.update(
                {
                    key: value
                    for key, value in normalized.items()
                    if not str(key).startswith("__")
                    and cls._canonical_spec_key(key) in replaced_targets
                }
            )
        return result

    @classmethod
    def _spec_display(cls, specs: dict[str, Any], change: CatalogBulkChange) -> dict[str, Any]:
        _normalized, targets = cls._spec_targets(change.specs)
        return {
            key: next(
                (
                    value
                    for raw_key, value in (specs or {}).items()
                    if cls._canonical_spec_key(raw_key) == key
                ),
                None,
            )
            for key in sorted(targets)
        }

    @classmethod
    def _spec_projection_patch(
        cls,
        specs: dict[str, Any],
        change: CatalogBulkChange,
    ) -> dict[str, Any]:
        _normalized, targets = cls._spec_targets(change.specs)
        patch: dict[str, Any] = {}
        if {"inverter", "inverter_type"} & targets:
            value = specs.get("inverter")
            if value in (None, ""):
                value = specs.get("compressor_type_norm", specs.get("inverter_type"))
            if value in (None, ""):
                patch["is_inverter"] = False
            elif isinstance(value, bool):
                patch["is_inverter"] = value
            elif str(value).strip().casefold() in {"true", "1", "yes", "да", "есть", "inverter", "инверторный"}:
                patch["is_inverter"] = True
            elif str(value).strip().casefold() in {"false", "0", "no", "нет", "on_off", "обычный"}:
                patch["is_inverter"] = False
            else:
                raise ValueError("Не удалось определить инверторность из характеристики.")
        if {"capacity_cooling_kw", "power_cooling"} & targets:
            value = specs.get("capacity_cooling_kw", specs.get("power_cooling"))
            if value in (None, ""):
                patch["power_cooling"] = None
            else:
                try:
                    patch["power_cooling"] = float(str(value).replace(",", "."))
                except (TypeError, ValueError) as exc:
                    raise ValueError("Не удалось определить мощность охлаждения из характеристики.") from exc
        return patch

    @staticmethod
    async def _validate_change(session: AsyncSession, change: CatalogBulkChange) -> None:
        if change.kind == "specs":
            CatalogBulkService._spec_targets(change.specs)
            return
        if change.kind == "relations":
            brand = await session.get(Brand, change.brand_id) if change.brand_id is not None else None
            if change.brand_id is not None and brand is None:
                raise ValueError("Выбранный бренд не найден.")
            series = await session.get(ProductSeries, change.series_id) if change.series_id is not None else None
            if change.series_id is not None and series is None:
                raise ValueError("Выбранная серия не найдена.")
            if series is not None and series.brand_id != change.brand_id:
                raise ValueError("Выбранная серия не принадлежит выбранному бренду.")
            return
        if change.kind == "features":
            if len(change.feature_ids) != len(set(change.feature_ids)):
                raise ValueError("Фича не может быть выбрана дважды.")
            features = list(
                (
                    await session.execute(
                        select(Feature).where(
                            Feature.id.in_(change.feature_ids),
                            Feature.is_active.is_(True),
                            Feature.archived_at.is_(None),
                        )
                    )
                ).scalars().all()
            )
            missing = sorted(set(change.feature_ids) - {int(feature.id) for feature in features if feature.id is not None})
            if missing:
                raise ValueError(f"Фичи не найдены или архивированы: {missing}")

    @classmethod
    async def _snapshot(cls, session: AsyncSession, ids: list[int]) -> dict[int, dict]:
        products = await ProductDAO.get_by_ids(session, ids)
        if len(products) != len(ids):
            raise CatalogBulkConflict("Часть товаров больше недоступна. Обновите выбор.")
        features = await FeatureResolverService.resolve_for_products(session, products)
        links = list((await session.execute(select(FeatureProductLink).where(FeatureProductLink.product_id.in_(ids)))).scalars().all())
        return {int(p.id): {
            "title": p.title, "brand_id": p.brand_id, "series_id": p.series_id,
            "brand": {"id": p.brand_id, "title": p.brand.title if p.brand else None},
            "series": {"id": p.series_id, "title": p.series.title if p.series else None},
            "is_published": p.is_published, "category": p.catalog_category_override,
            "is_inverter": p.is_inverter, "power_cooling": p.power_cooling,
            "specs": p.specs or {}, "tags": sorted(t.id for t in p.tags),
            "features": sorted(item.model_dump(mode="json")["id"] for item in features.get(p.id, {}).get("effective", [])),
            "assignments": sorted(
                [cls._assignment_snapshot(link) for link in links if link.product_id == p.id],
                key=lambda item: item["feature_id"],
            ),
        } for p in products}

    @staticmethod
    def _display(state: dict, change: CatalogBulkChange) -> dict:
        if change.kind == "relations":
            return {key: state[key] for key in ("brand", "series", "features")}
        if change.kind == "publication":
            return {"is_published": state["is_published"]}
        if change.kind == "category":
            return {"category": state["category"], "tags": state["tags"]}
        if change.kind == "features":
            return {"features": state["features"], "assignments": [{"feature_id": item["feature_id"], "is_enabled": item["is_enabled"]} for item in state["assignments"]]}
        result = CatalogBulkService._spec_display(state["specs"], change)
        _normalized, targets = CatalogBulkService._spec_targets(change.specs)
        if {"inverter", "inverter_type"} & targets:
            result["is_inverter"] = state["is_inverter"]
        if {"capacity_cooling_kw", "power_cooling"} & targets:
            result["power_cooling"] = state["power_cooling"]
        return result

    @staticmethod
    async def _stage(session: AsyncSession, ids: list[int], change: CatalogBulkChange) -> None:
        await CatalogBulkService._validate_change(session, change)
        products = await ProductDAO.get_by_ids(session, ids)
        for product in products:
            patch: dict[str, Any] = {}
            if change.kind == "relations":
                patch = {"brand_id": change.brand_id, "series_id": change.series_id}
            elif change.kind == "publication":
                patch = {"is_published": change.is_published}
            elif change.kind == "category":
                patch = {"catalog_category_override": change.category}
            elif change.kind == "specs":
                specs = CatalogBulkService._specs_after_change(product.specs or {}, change)
                patch = {
                    "specs": specs,
                    **CatalogBulkService._spec_projection_patch(specs, change),
                }
            else:
                workspace = await FeatureAssignmentService.get_product_workspace(session, product.id)
                assignments = {item.feature_id: item for item in workspace.manual_assignments}
                for feature_id in change.feature_ids:
                    if change.feature_mode == "inherit":
                        assignments.pop(feature_id, None)
                    else:
                        prior = assignments.get(feature_id)
                        assignments[feature_id] = prior.model_copy(update={"is_enabled": change.feature_mode == "add"}) if prior else FeatureLinkPayload(feature_id=feature_id, source="manual", is_enabled=change.feature_mode == "add")
                await FeatureAssignmentService.replace_product_assignments(session, product.id, list(assignments.values()), commit=False)
            if patch:
                await ProductWriteService.update_product(
                    session,
                    product.id,
                    patch,
                    commit=False,
                    sync_derived_fields=False,
                )
        await session.flush()

    @classmethod
    async def preview(cls, session: AsyncSession, request: CatalogBulkPreviewRequest, actor: str) -> dict:
        ids = sorted(set(request.product_ids))
        if any(pid <= 0 for pid in ids):
            raise ValueError("Некорректный идентификатор товара")
        await cls._validate_change(session, request.change)
        before = await cls._snapshot(session, ids)
        nested = await session.begin_nested()
        try:
            await cls._stage(session, ids, request.change)
            # Reload changed relations after FK updates within the preview transaction.
            session.expire_all()
            after = await cls._snapshot(session, ids)
            items = [{"product_id": pid, "title": before[pid]["title"], "before": cls._display(before[pid], request.change), "after": cls._display(after[pid], request.change), "changed": digest(before[pid]) != digest(after[pid])} for pid in ids]
        finally:
            await nested.rollback()
            session.expire_all()
        return {"items": items, "changed_count": sum(item["changed"] for item in items), "token": sign_preview({"actor": actor, "ids": ids, "change": request.change.model_dump(), "fingerprints": {str(pid): digest(before[pid]) for pid in ids}}), "expires_in_seconds": 900}

    @classmethod
    async def apply(cls, session: AsyncSession, token: str, actor: str) -> dict:
        payload = read_preview(token, actor)
        ids = sorted({int(product_id) for product_id in payload["ids"]})
        if not ids or len(ids) > 500:
            raise ValueError("Предпросмотр устарел или недействителен. Рассчитайте изменения заново.")
        try:
            locked_ids = set(
                (await session.execute(
                    select(Product.id).where(Product.id.in_(ids)).order_by(Product.id).with_for_update()
                )).scalars().all()
            )
            if locked_ids != set(ids):
                raise CatalogBulkConflict("Часть товаров больше недоступна. Обновите выбор.")
            session.expire_all()
            before = await cls._snapshot(session, ids)
            if any(digest(before[pid]) != payload["fingerprints"][str(pid)] for pid in ids):
                raise CatalogBulkConflict("Товары изменились после предпросмотра. Рассчитайте изменения заново.")
            await cls._stage(session, ids, CatalogBulkChange.model_validate(payload["change"]))
            session.expire_all()
            after = await cls._snapshot(session, ids)
            changed = [pid for pid in ids if digest(before[pid]) != digest(after[pid])]
            await session.commit()
            return {"updated": len(changed), "product_ids": changed}
        except Exception:
            await session.rollback()
            raise
