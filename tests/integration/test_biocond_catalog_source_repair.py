"""Real PostgreSQL CLI transaction: rollback, creation, exact rerun and preservation."""
from copy import deepcopy
import json
import re
from urllib.parse import quote

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import select

from crud.catalog_revision import CatalogRevisionDAO
from models import (Brand, Product, ProductSeries, Feature, FeatureCategory,
                    FeatureProductLink, FeatureSeriesLink, CatalogDocument,
                    IntegrationOutboxEvent)
from scripts.repair_biocond_catalog import run
from services.catalog_biocond_source_repair import digest, link_projection, present, spec_families
from services.catalog_revision_service import CatalogRevisionService


def fixture_catalog():
    brands = [Brand(id=id, slug=f'brand-{id}', title=f'Brand {id}') for id in [1, 3, 14]]
    series = ProductSeries(id=901, brand_id=1, slug='old', title='Keep title', description='old series', features=['Contradictory legacy claim'], seo_title='Keep SEO', gallery_images=['https://example.invalid/keep.webp'])
    category = FeatureCategory(id=1, slug='comfort', name='Comfort')
    feature = Feature(id=902, slug='generic-safe', name='Generic safe', category_id=1, scope_type='universal')
    products = [Product(id=9001, brand_id=1, series_id=901, title='Keep MDV title', slug='mdv-product', description='old MDV', power_cooling=2.5, specs={'capacity_cooling_kw': '2.5', 'capacity_cooling_min_kw': '0.70 kW', 'capacity_cooling_max_kw': '4 kW', 'custom': {'exact': True}, '__filter_custom': 77, '__typed_specs': {'custom': {'value': 'preserve'}, 'capacity_cooling_kw': {'value': 25}}}, price=1234, product_kind='other', main_image='https://example.invalid/keep.webp'), Product(id=9002, brand_id=14, title='Keep MHI title', slug='mhi-product', description='old MHI', series_assignment_source='derived', specs={'custom': True}, price=2345)]
    link = FeatureProductLink(id=500, product_id=9001, feature_id=902, override_image_url='https://example.invalid/keep-link.webp')
    m = {'schema_version': 1, 'scope': {'brand_ids': [1, 3, 14], 'product_ids': [9001, 9002], 'series_ids': [901]}, 'sources': {'fixture': 'https://mhi.by/'}, 'brands': [{'identity': {'id': b.id, 'slug': b.slug, 'title': b.title}, 'before_sha256': {'official_url': digest(None)}, 'fields_set': {'official_url': 'https://mhi.by/'} if b.id == 14 else {}} for b in brands], 'series': [{'identity': {'id': 901, 'brand_id': 1, 'slug': 'old'}, 'before_sha256': {'description': digest('old series'), 'features': digest(['Contradictory legacy claim'])}, 'fields_set': {'description': 'new series prose', 'features': ['Reviewed legacy prose']}}], 'products': [], 'new_series': [{'key': 'mhi-new', 'identity': {'brand_id': 14, 'slug': 'exact-w-generation'}, 'before': {'present': False}, 'fields_set': {'title': 'Exact W generation', 'description': 'Reviewed family', 'short_description': 'Reviewed short', 'source_url': 'https://mhi.by/reviewed.pdf'}}], 'new_features': [{'key': 'mhi-air', 'identity': {'brand_id': 14, 'slug': 'mhi-exact-air'}, 'before': {'present': False}, 'fields_set': {'name': 'Exact air', 'category_id': 1, 'scope_type': 'brand', 'is_active': True, 'full_description': 'Reviewed feature', 'source_url': 'https://mhi.by/reviewed.pdf', 'source_notes': 'PDF page21'}}], 'documents': [{'identity': {'brand_id': 14, 'url': 'https://mhi.by/reviewed.pdf'}, 'before': {'present': False}, 'fields_set': {'title': 'Reviewed catalog', 'kind': 'catalog', 'source_url': 'https://mhi.by/', 'year': 2026, 'visibility': 'public'}}], 'manual_links_before': [link_projection(link, 'product')], 'feature_links': [{'kind': 'product', 'target': {'id': 9001}, 'feature': {'id': 902}, 'before': {'present': True, 'value': link_projection(link, 'product')['fields']}, 'fields_set': {'source': 'manual', 'is_enabled': False, 'override_footnote': 'Exact reviewed exclusion'}}, {'kind': 'series', 'target': {'series_key': 'mhi-new'}, 'feature': {'feature_key': 'mhi-air'}, 'before': {'present': False}, 'fields_set': {'source': 'manual', 'is_enabled': True, 'is_featured': True, 'display_mode': 'detailed', 'override_description': 'Exact scope'}}]}
    for product in products:
        row = {'identity': {'id': product.id, 'brand_id': product.brand_id, 'slug': product.slug, 'title': product.title}, 'specs_set': {'capacity_cooling_kw': '3.5'} if product.id == 9001 else {}, 'specs_delete': [], 'rebuild_typed': ['capacity_cooling_kw'] if product.id == 9001 else [], 'fields_set': {'power_cooling': 3.5, 'description': 'new MDV'} if product.id == 9001 else {'series_assignment_source': 'manual'}, 'before': {'specs': {}, 'typed': {}, 'filters': {}, 'fields_sha256': {}}}
        if product.id == 9002:
            row['series_key'] = 'mhi-new'
        keys, filters = spec_families(row)
        row['before'] = {'specs': {k: present(product.specs, k) for k in keys}, 'typed': {k: present(product.specs.get('__typed_specs', {}), k) for k in keys}, 'filters': {k: present(product.specs, k) for k in filters}, 'fields_sha256': {key: digest(getattr(product, key)) for key in row['fields_set']}}
        row['before']['fields_sha256']['series_ref'] = digest('id:901' if product.id == 9001 else None)
        row['source_before_sha256'] = digest(row['before'])
        m['products'].append(row)
    return m, brands, series, category, feature, products, link


async def snapshot(factory):
    async with factory() as session:
        result = {}
        for model in (Brand, Product, ProductSeries, Feature, FeatureProductLink, FeatureSeriesLink, CatalogDocument):
            result[model.__tablename__] = [obj.model_dump(mode='json') for obj in (await session.execute(select(model).order_by(model.id))).scalars()]
        revision = await CatalogRevisionDAO.get_current(session)
        events = list((await session.execute(select(IntegrationOutboxEvent).order_by(IntegrationOutboxEvent.event_id))).scalars())
        return deepcopy({**result, 'revision': revision.revision, 'events': [event.model_dump(mode='json') for event in events]})


@pytest.mark.asyncio
async def test_cli_atomic_rollback_success_noop_and_preserved_unrelated_state(db_engine, monkeypatch, tmp_path):
    assert db_engine.dialect.name == 'postgresql'
    assert re.search(r'(?:^|_)test(?:_|$)', db_engine.url.database)
    factory = sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    import core.database
    monkeypatch.setattr(core.database, 'async_session_maker', factory)
    m, brands, series, category, feature, products, link = fixture_catalog()
    async with factory() as session:
        session.add_all(brands + [category])
        await session.flush()
        session.add_all([series, feature])
        await session.flush()
        session.add_all(products)
        await session.flush()
        session.add(link)
        await session.commit()
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(m))
    baseline = await snapshot(factory)
    plan = await run(manifest_path=path)
    assert plan['changed'] > 0 and await snapshot(factory) == baseline
    reviewed = tmp_path / 'reviewed.json'
    reviewed.write_text(json.dumps(plan))
    real_staging = CatalogRevisionService.stage_invalidation
    staged = []

    async def fail_after_staging(session, **kwargs):
        result = await real_staging(session, **kwargs)
        assert result['revision'] == 1
        assert len(list((await session.execute(select(IntegrationOutboxEvent))).scalars())) == 1
        assert (await session.get(Product, 9001)).specs['__typed_specs']['capacity_cooling_kw']['max'] == 4
        staged.append(True)
        raise RuntimeError('after real revision/outbox staging')

    with monkeypatch.context() as failure:
        failure.setattr(CatalogRevisionService, 'stage_invalidation', fail_after_staging)
        with pytest.raises(RuntimeError, match='after real revision/outbox staging'):
            await run(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=plan['plan_digest'])
    assert staged == [True] and await snapshot(factory) == baseline
    result = await run(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=plan['plan_digest'])
    assert result['changed'] == plan['changed'] and result['revision']['revision'] == 1
    after = await snapshot(factory)
    assert after['revision'] == 1 and len(after['events']) == 1
    paths = after['events'][0]['payload']['paths']
    assert set(paths) == set(plan['series_paths']) | {f'/product/{quote(p.slug, safe="")}/' for p in products} | {'/brands/', '/catalog/'} | {f'/brands/{b.slug}/' for b in brands}
    assert len(after['product_series']) == 2 and len(after['feature']) == 2 and len(after['catalog_document']) == 1
    for before, product in zip(baseline['product'], after['product']):
        for field in ('title', 'price', 'main_image', 'product_kind', 'slug'):
            assert product[field] == before[field]
        assert product['specs']['custom'] == before['specs']['custom']
    repaired = after['product'][0]['specs']
    assert repaired['__typed_specs']['custom'] == {'value': 'preserve'}
    assert repaired['__filter_custom'] == 77
    assert repaired['capacity_cooling_min_kw'] == '0.70 kW'
    assert repaired['__typed_specs']['capacity_cooling_kw']['min'] == .7
    assert after['feature_product_link'][0]['is_enabled'] is False
    assert after['feature_product_link'][0]['override_image_url'].endswith('keep-link.webp')
    old_series = next(s for s in after['product_series'] if s['id'] == 901)
    assert old_series['seo_title'] == 'Keep SEO'
    assert old_series['features'] == ['Reviewed legacy prose']
    assert old_series['gallery_images'] == ['https://example.invalid/keep.webp']
    noop = await run(manifest_path=path)
    assert noop['changed'] == 0
    reviewed.write_text(json.dumps(noop))
    repeated = await run(manifest_path=path, execute=True, reviewed_plan=reviewed, execute_plan_digest=noop['plan_digest'])
    assert repeated['revision'] is None and repeated['changed'] == 0
    assert await snapshot(factory) == after
