"""Meaningful exact-state and isolation guards for the bounded source repair."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from services.catalog_biocond_source_repair import (
    RepairBlocked, build_plan, desired_projection, digest, link_projection,
    present, repaired_specs, spec_families, validate_reviewed_plan,
)

NOW = datetime(2026, 10, 20, tzinfo=timezone.utc)


def fixture_catalog():
    from models import Brand, Product, ProductSeries, Feature, FeatureCategory
    brands = [Brand(id=id, slug=f'brand-{id}', title=f'Brand {id}') for id in [1, 3, 14]]
    series = ProductSeries(id=901, brand_id=1, slug='old', title='Old', description='before')
    specs = {'capacity_cooling_kw': '2.5', 'capacity_cooling_min_kw': '0.70 kW', 'capacity_cooling_max_kw': '4.00 kW', 'unrelated': {'keep': True}, '__filter_other': 91, '__typed_specs': {'unrelated': {'value': 'leave alone'}, 'capacity_cooling_kw': {'value': 25}}}
    product = Product(id=9001, brand_id=1, series_id=901, slug='product', title='Exact product', description='old', specs=specs, power_cooling=2.5, series_assignment_source='derived')
    feature = Feature(id=902, slug='safe-feature', name='Safe feature', category_id=1, scope_type='universal', is_active=True)
    row = {'identity': {'id': product.id, 'brand_id': 1, 'slug': product.slug, 'title': product.title}, 'specs_set': {'capacity_cooling_kw': '3.5'}, 'specs_delete': [], 'rebuild_typed': ['capacity_cooling_kw'], 'fields_set': {'power_cooling': 3.5, 'description': 'new'}, 'before': {'specs': {}, 'typed': {}, 'filters': {}, 'fields_sha256': {'power_cooling': digest(2.5), 'description': digest('old'), 'series_ref': digest('id:901')}}}
    keys, filters = spec_families(row)
    row['before'].update(specs={k: present(specs, k) for k in keys}, typed={k: present(specs['__typed_specs'], k) for k in keys}, filters={k: present(specs, k) for k in filters})
    row['source_before_sha256'] = digest(row['before'])
    m = {'schema_version': 1, 'scope': {'brand_ids': [1, 3, 14], 'product_ids': [9001], 'series_ids': [901]}, 'sources': {'fixture': True}, 'brands': [{'identity': {'id': b.id, 'slug': b.slug, 'title': b.title}, 'before_sha256': {}, 'fields_set': {}} for b in brands], 'products': [row], 'series': [{'identity': {'id': 901, 'brand_id': 1, 'slug': 'old'}, 'before_sha256': {'description': digest('before')}, 'fields_set': {'description': 'after'}}], 'new_series': [], 'new_features': [], 'documents': [], 'feature_links': [], 'manual_links_before': []}
    c = dict(brands=brands, products=[product], series=[series], features=[feature], categories=[FeatureCategory(id=1, slug='comfort', name='Comfort')], documents=[], links=[])
    return m, c


def test_plan_is_read_only_and_rebuilds_only_touched_families_with_companion_bounds():
    m, c = fixture_catalog()
    original = deepcopy(c['products'][0].specs)
    plan = build_plan(m, c, now=NOW)
    assert plan['ready'] and plan['changed'] == 2
    assert c['products'][0].specs == original
    updated = repaired_specs(original, m['products'][0])
    assert updated['capacity_cooling_min_kw'] == '0.70 kW'
    assert updated['capacity_cooling_max_kw'] == '4.00 kW'
    assert updated['__typed_specs']['capacity_cooling_kw']['min'] == .7
    assert updated['__typed_specs']['capacity_cooling_kw']['max'] == 4
    assert updated['__typed_specs']['capacity_cooling_kw']['nominal'] == 3.5
    for key in ('unrelated', '__filter_other'):
        assert updated[key] == original[key]
    assert updated['__typed_specs']['unrelated'] == original['__typed_specs']['unrelated']


def test_wifi_and_deleted_family_do_not_overwrite_unrelated_filters():
    row = {'specs_set': {'wifi_state': 'ready'}, 'specs_delete': ['ionizer'], 'rebuild_typed': ['wifi_state', 'ionizer']}
    old = {'wifi_ready': True, 'wifi_state': 'builtin', 'wifi_builtin': True, 'ionizer': True, '__filter_wifi_builtin': True, '__filter_other': 8, '__typed_specs': {'ionizer': {'value': True}, 'other': {'value': 9}}}
    new = repaired_specs(old, row)
    assert new['wifi_state'] == 'ready' and new['wifi_builtin'] is False
    assert new['__filter_wifi_builtin'] is False
    assert new['__filter_other'] == 8 and new['__typed_specs']['other'] == {'value': 9}
    assert 'ionizer' not in new and 'ionizer' not in new['__typed_specs']


@pytest.mark.parametrize('change', ['extra_product', 'missing_product', 'extra_series', 'identity', 'partial', 'unknown_field', 'guard', 'incoherent_power'])
def test_rejects_unknown_scope_partial_states_and_unsafe_fields(change):
    m, c = fixture_catalog()
    if change == 'extra_product':
        c['products'].append(SimpleNamespace(id=999, brand_id=1))
    elif change == 'missing_product':
        c['products'] = []
    elif change == 'extra_series':
        c['series'].append(SimpleNamespace(id=999, brand_id=1))
    elif change == 'identity':
        c['products'][0].title = 'changed by someone else'
    elif change == 'partial':
        c['series'][0].description = 'after'
    elif change == 'unknown_field':
        m['products'][0]['fields_set']['price'] = 1
    elif change == 'guard':
        m['products'][0]['before']['typed'].clear()
        m['products'][0]['source_before_sha256'] = digest(m['products'][0]['before'])
    else:
        m['products'][0]['fields_set']['power_cooling'] = 35
    with pytest.raises(RepairBlocked):
        build_plan(m, c, now=NOW)


def test_rejects_new_manual_state_and_derived_or_inactive_feature():
    from models import FeatureProductLink
    m, c = fixture_catalog()
    link = FeatureProductLink(id=5, product_id=9001, feature_id=902)
    c['links'] = [('product', link)]
    with pytest.raises(RepairBlocked, match='unknown or partially'):
        build_plan(m, c, now=NOW)
    c['links'] = []
    m['feature_links'] = [{'kind': 'product', 'target': {'id': 9001}, 'feature': {'id': 902}, 'before': {'present': False}, 'fields_set': {'source': 'manual', 'is_enabled': False}}]
    for active, scope in [(False, 'universal'), (True, 'derived')]:
        c['features'][0].is_active, c['features'][0].scope_type = active, scope
        with pytest.raises(RepairBlocked, match='active, nonderived'):
            build_plan(m, c, now=NOW)


def test_link_guard_preserves_id_media_and_false_exclusions():
    from models import FeatureProductLink
    m, c = fixture_catalog()
    link = FeatureProductLink(id=50, product_id=9001, feature_id=902, override_image_url='https://example.invalid/keep.webp')
    baseline = link_projection(link, 'product')
    m['manual_links_before'] = [baseline]
    c['links'] = [('product', link)]
    m['feature_links'] = [{'kind': 'product', 'target': {'id': 9001}, 'feature': {'id': 902}, 'before': {'present': True, 'value': baseline['fields']}, 'fields_set': {'is_enabled': False, 'override_footnote': 'Exact source'}}]
    plan = build_plan(m, c, now=NOW)
    assert plan['changed'] == 3
    assert baseline['id'] == 50 and baseline['fields']['override_image_url'].endswith('keep.webp')
    link.override_title = 'New manual change'
    with pytest.raises(RepairBlocked):
        build_plan(m, c, now=NOW)


def test_review_requires_exact_fresh_digest_manifest_and_state():
    m, c = fixture_catalog()
    reviewed = build_plan(m, c, now=NOW)
    live = build_plan(m, c, now=NOW + timedelta(minutes=1))
    validate_reviewed_plan(reviewed, live, reviewed['plan_digest'], now=NOW + timedelta(minutes=1))
    with pytest.raises(RepairBlocked, match='expired'):
        validate_reviewed_plan(reviewed, live, reviewed['plan_digest'], now=NOW + timedelta(minutes=30))
    with pytest.raises(RepairBlocked, match='digest'):
        validate_reviewed_plan(reviewed, live, '0' * 64, now=NOW)
    for field in ('manifest_sha256', 'state_digest'):
        changed = {**live, field: '0' * 64}
        with pytest.raises(RepairBlocked, match='changed'):
            validate_reviewed_plan(reviewed, changed, reviewed['plan_digest'], now=NOW)


def test_primary_must_be_positively_verified():
    from scripts.repair_biocond_catalog import require_primary
    for state in [True, None, 0, 'false']:
        with pytest.raises(RepairBlocked):
            require_primary(True, state)
    require_primary(True, False)
    require_primary(False, True)


def test_natural_key_creation_complete_targets_and_symbolic_rerun_noop():
    from models import CatalogDocument, Feature, FeatureSeriesLink, ProductSeries
    m, c = fixture_catalog()
    m['new_series'] = [{'key': 'new', 'identity': {'brand_id': 1, 'slug': 'new'}, 'before': {'present': False}, 'fields_set': {'title': 'New series', 'source_url': 'https://example.invalid/catalog.pdf'}}]
    m['new_features'] = [{'key': 'new-air', 'identity': {'brand_id': 1, 'slug': 'new-air'}, 'before': {'present': False}, 'fields_set': {'name': 'New air', 'category_id': 1, 'scope_type': 'brand', 'is_active': True, 'source_url': 'https://example.invalid/catalog.pdf'}}]
    m['documents'] = [{'identity': {'brand_id': 1, 'url': 'https://example.invalid/catalog.pdf'}, 'before': {'present': False}, 'fields_set': {'title': 'Official source', 'source_url': 'https://example.invalid/'}}]
    m['feature_links'] = [{'kind': 'series', 'target': {'series_key': 'new'}, 'feature': {'feature_key': 'new-air'}, 'before': {'present': False}, 'fields_set': {'source': 'manual', 'is_enabled': True, 'is_featured': True}}]
    row = m['products'][0]
    row['series_key'] = 'new'
    row['fields_set']['series_assignment_source'] = 'manual'
    row['before']['fields_sha256']['series_assignment_source'] = digest('derived')
    row['source_before_sha256'] = digest(row['before'])
    assert build_plan(m, c, now=NOW)['changed'] == 6
    new_series = ProductSeries(id=991, **m['new_series'][0]['identity'], **m['new_series'][0]['fields_set'])
    new_feature = Feature(id=992, **m['new_features'][0]['identity'], **m['new_features'][0]['fields_set'])
    new_document = CatalogDocument(id=993, **m['documents'][0]['identity'], **m['documents'][0]['fields_set'])
    c['series'].append(new_series)
    c['features'].append(new_feature)
    c['documents'].append(new_document)
    c['links'] = [('series', FeatureSeriesLink(id=994, series_id=991, feature_id=992, source='manual', is_enabled=True, is_featured=True))]
    product = c['products'][0]
    product.specs = repaired_specs(product.specs, row)
    for key, value in row['fields_set'].items():
        setattr(product, key, value)
    product.series_id = 991
    c['series'][0].description = 'after'
    assert build_plan(m, c, now=NOW)['changed'] == 0
    new_series.seo_title = 'Someone added manual state to an owned record'
    with pytest.raises(RepairBlocked, match='unknown or partially'):
        build_plan(m, c, now=NOW)


def test_existing_id_assignment_is_reviewed_and_manual():
    m, c = fixture_catalog()
    row = m['products'][0]
    row['series_key'] = 'id:901'
    row['fields_set']['series_assignment_source'] = 'manual'
    row['before']['fields_sha256']['series_assignment_source'] = digest('derived')
    row['source_before_sha256'] = digest(row['before'])
    assert build_plan(m, c, now=NOW)['ready']
    row['series_key'] = 'id:999'
    with pytest.raises(RepairBlocked, match='escapes'):
        build_plan(m, c, now=NOW)


def test_reviewed_legacy_series_feature_prose_array_is_allowed():
    m, c = fixture_catalog()
    c['series'][0].features = ['Contradictory legacy claim']
    m['series'][0]['before_sha256']['features'] = digest(c['series'][0].features)
    m['series'][0]['fields_set']['features'] = ['Source-confirmed function']
    assert build_plan(m, c, now=NOW)['ready']
    for invalid in ({'unknown': 'structure'}, [True], ['x'] * 101, ['x' * 2001]):
        m['series'][0]['fields_set']['features'] = invalid
        with pytest.raises(RepairBlocked, match='bounded list of strings'):
            build_plan(m, c, now=NOW)
    m['series'][0]['fields_set']['features'] = []
    assert build_plan(m, c, now=NOW)['ready']
    m['series'][0]['fields_set']['content_blocks'] = []
    with pytest.raises(RepairBlocked, match='Unreviewed'):
        build_plan(m, c, now=NOW)
