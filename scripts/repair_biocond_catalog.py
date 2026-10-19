"""Read-only Biocond catalog source plan; execute only its exact reviewed digest."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.catalog_biocond_source_repair import (  # noqa: E402
    BRAND_IDS, DEFAULT_MANIFEST, RepairBlocked, build_plan, load_manifest,
    repaired_specs, validate_reviewed_plan,
)


def require_primary(execute: bool, in_recovery: object) -> None:
    if execute and in_recovery is not False:
        raise RepairBlocked('Execute requires a positively verified PostgreSQL primary')


async def run(*, manifest_path: Path, execute=False, reviewed_plan=None, execute_plan_digest=None) -> dict:
    m = load_manifest(manifest_path)
    if execute and (reviewed_plan is None or not execute_plan_digest):
        raise RepairBlocked('Execute requires --reviewed-plan and --execute-plan-digest')
    if not execute and (reviewed_plan is not None or execute_plan_digest is not None):
        raise RepairBlocked('Review arguments require --execute')
    reviewed = json.loads(Path(reviewed_plan).read_text()) if execute else None
    from sqlalchemy import text
    from sqlalchemy.orm.attributes import flag_modified
    from sqlmodel import select
    from core.database import async_session_maker
    from models import (Brand, Product, ProductSeries, Feature, FeatureCategory,
                        FeatureBrandLink, FeatureSeriesLink, FeatureProductLink, CatalogDocument)
    from services.catalog_invalidation_commit_service import CatalogInvalidationCommitService

    async with async_session_maker() as session:
        await session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ' + ('' if execute else ', READ ONLY')))
        if execute:
            await session.execute(text("SET LOCAL lock_timeout = '5s'"))
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('biocond-source-repair-v1'))"))
        require_primary(execute, await session.scalar(text('SELECT pg_is_in_recovery()')))

        async def rows(model, condition=None):
            query = select(model).order_by(model.id)
            if condition is not None:
                query = query.where(condition)
            if execute:
                query = query.with_for_update(of=model)
            return list((await session.execute(query)).scalars())

        # Lock parents before links, including unchanged rows and every existing
        # series. Parent locks also serialize concurrent FK link insertions.
        brands = await rows(Brand, Brand.id.in_(BRAND_IDS))
        series = await rows(ProductSeries, ProductSeries.brand_id.in_(BRAND_IDS))
        products = await rows(Product, Product.brand_id.in_(BRAND_IDS))
        features = await rows(Feature)
        categories = await rows(FeatureCategory)
        documents = await rows(CatalogDocument, CatalogDocument.brand_id.in_(BRAND_IDS))
        links = []
        for kind, model, ids in [('brand', FeatureBrandLink, BRAND_IDS), ('series', FeatureSeriesLink, [s.id for s in series]), ('product', FeatureProductLink, [p.id for p in products])]:
            links.extend((kind, obj) for obj in await rows(model, getattr(model, kind + '_id').in_(ids)))
        catalog = dict(brands=brands, series=series, products=products, features=features, categories=categories, documents=documents, links=links)
        plan = build_plan(m, catalog)
        if not execute:
            await session.rollback()
            return plan
        validate_reviewed_plan(reviewed, plan, execute_plan_digest)
        if not plan['changed']:
            await session.rollback()
            return {'mode': 'execute', 'changed': 0, 'reviewed_plan_digest': execute_plan_digest, 'revision': None}

        maps = {kind: {obj.id: obj for obj in catalog[kind]} for kind in ('brands', 'series', 'products', 'features')}
        refs = {'series': {}, 'features': {}}
        new_models = {'new_series': (ProductSeries, 'series'), 'new_features': (Feature, 'features'), 'documents': (CatalogDocument, 'documents')}
        for kind, (model, source) in new_models.items():
            for row in m.get(kind, []):
                obj = next((obj for obj in catalog[source] if all(getattr(obj, k) == v for k, v in row['identity'].items())), None)
                if obj is None:
                    obj = model(**row['identity'], **row['fields_set'])
                    session.add(obj)
                    await session.flush()
                if kind != 'documents':
                    refs[source][row['key']] = obj.id
                    maps[source][obj.id] = obj
        patches = {kind: {r['identity']['id']: r for r in m[kind]} for kind in ('products', 'series', 'brands')}
        patches['features'] = {r['identity']['id']: r for r in m.get('reviewed_features', [])}
        for op in plan['operations']:
            kind = op['kind']
            if kind not in patches:
                continue
            obj, row = maps[kind][op['ref']], patches[kind][op['ref']]
            if kind == 'products':
                updated = repaired_specs(obj.specs or {}, row)
                if updated != obj.specs:
                    obj.specs = updated
                    flag_modified(obj, 'specs')
                assignment = row.get('series_key')
                if assignment is not None:
                    obj.series_id = int(assignment[3:]) if assignment.startswith('id:') else refs['series'][assignment.removeprefix('key:')]
            for key, val in row['fields_set'].items():
                setattr(obj, key, val)
            session.add(obj)
        # Every existing unmentioned link is retained byte-for-byte. An explicit
        # false exclusion is an upsert, never a deletion or a set replacement.
        for row in m.get('feature_links', []):
            kind = row['kind']
            target = row['target']
            owner_id = target.get('id') if 'id' in target else refs['series'][target['series_key']]
            feature = row['feature']
            feature_id = feature.get('id') if 'id' in feature else refs['features'][feature['feature_key']]
            obj = next((obj for link_kind, obj in links if link_kind == kind and getattr(obj, kind + '_id') == owner_id and obj.feature_id == feature_id), None)
            if obj is None:
                model = FeatureSeriesLink if kind == 'series' else FeatureProductLink
                obj = model(**{kind + '_id': owner_id, 'feature_id': feature_id})
            for key, val in row['fields_set'].items():
                setattr(obj, key, val)
            session.add(obj)
        await session.flush()
        revision = await CatalogInvalidationCommitService.commit_global_mutation(
            session, reason='biocond_source_catalog_repair', product_ids=plan['product_ids'],
            brand_slugs=plan['brand_slugs'], additional_paths=plan['series_paths'],
        )
        return {'mode': 'execute', 'changed': plan['changed'], 'reviewed_plan_digest': execute_plan_digest, 'revision': revision}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--reviewed-plan', type=Path)
    parser.add_argument('--execute-plan-digest')
    args = parser.parse_args()
    try:
        result = asyncio.run(run(manifest_path=args.manifest, execute=args.execute, reviewed_plan=args.reviewed_plan, execute_plan_digest=args.execute_plan_digest))
    except (RepairBlocked, ValueError, KeyError) as exc:
        print(json.dumps({'ready': False, 'blocked': str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
