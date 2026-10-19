"""Exact, reviewed Biocond catalog repair; never an arbitrary table patcher."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from services.spec_normalizer import normalize_specs
from services.spec_registry import SPEC_DEFINITIONS, build_typed_specs

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / 'config/catalog_source_repairs/biocond-2026.json'
BRAND_IDS = {1, 3, 14}
PRODUCT_FIELDS = {'description', 'power_cooling', 'source_url', 'series_assignment_source'}
SERIES_FIELDS = {'title', 'description', 'short_description', 'source_url', 'features'}
FEATURE_FIELDS = {'name', 'category_id', 'scope_type', 'is_active', 'short_description', 'full_description', 'source_url', 'source_notes', 'footnote', 'icon_caption', 'sort_order', 'aliases'}
REVIEWED_FEATURE_COPY_FIELDS = {'short_description', 'full_description', 'source_url', 'source_notes'}
DOCUMENT_FIELDS = {'title', 'kind', 'source_url', 'year', 'language', 'visibility', 'inherit_to_products', 'sort_order'}
LINK_FIELDS = {'source', 'is_enabled', 'sort_order', 'display_mode', 'override_title', 'override_description', 'override_media_id', 'override_image_url', 'override_icon', 'override_footnote'}
LINK_EDITS = LINK_FIELDS - {'override_media_id', 'override_image_url', 'override_icon'}
WIFI_RAW = {'wifi_ready', 'wifi_state', 'wifi_builtin'}
FILTER_FAMILIES = {'noise_indoor': {'__filter_noise_min'}, 'temp_range_heat': {'__filter_min_heat'}, 'inverter': {'compressor_type_norm'}, 'indoor_type': {'__filter_indoor_type'}}
for _key in WIFI_RAW:
    FILTER_FAMILIES[_key] = {'__filter_wifi', '__filter_wifi_builtin'}


class RepairBlocked(ValueError):
    """Reviewed identities, state or source manifest no longer match."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def present(mapping: dict, key: str) -> dict:
    return {'present': key in mapping, **({'value': deepcopy(mapping[key])} if key in mapping else {})}


def _identity(obj, identity):
    if any(getattr(obj, key, None) != val for key, val in identity.items()):
        raise RepairBlocked(f'Identity changed: {identity}')


def link_projection(obj, kind: str, *, target: str | None = None, feature: str | None = None) -> dict:
    """Canonical baseline includes ID and every durable link field, no timestamps."""
    keys = LINK_FIELDS | ({'is_featured'} if kind == 'series' else set())
    return {'id': obj.id, 'kind': kind, 'target': target or f'id:{getattr(obj, kind + "_id")}', 'feature': feature or f'id:{obj.feature_id}', 'fields': {key: deepcopy(getattr(obj, key)) for key in sorted(keys)}}


def spec_families(row: dict) -> tuple[set[str], set[str]]:
    keys = set(row.get('rebuild_typed', []))
    if keys & WIFI_RAW:
        keys |= WIFI_RAW
    # Numeric families carry bounds in companion raw keys. Keep these raw values
    # intact while giving the typed builder the complete touched family.
    for nominal in ('capacity_cooling_kw', 'capacity_heating_kw', 'power_cons_cooling_kw', 'power_cons_heating_kw'):
        prefix = nominal[:-3]
        family = {nominal, prefix + '_min_kw', prefix + '_max_kw'}
        if keys & family:
            keys |= family
    filters = set().union(*(FILTER_FAMILIES.get(key, set()) for key in keys))
    filters |= {f'__filter_{key}' for key in row.get('specs_delete', [])}
    return keys, filters


def repaired_specs(specs: dict, row: dict) -> dict:
    """Normalize touched families only and preserve all unrelated durable layers."""
    result = deepcopy(specs)
    edits = set(row.get('specs_set', {})) | set(row.get('specs_delete', []))
    if not edits and not row.get('rebuild_typed'):
        return result
    keys, filters = spec_families(row)
    values = {key: deepcopy(result[key]) for key in keys if key in result}
    values.update(deepcopy(row.get('specs_set', {})))
    for key in row.get('specs_delete', []):
        values.pop(key, None)
    if keys & WIFI_RAW:
        state = values.get('wifi_state', values.get('wifi_ready'))
        for key in WIFI_RAW:
            values.pop(key, None)
        values['wifi_ready'] = state
    normalized = normalize_specs(values)
    raw_updates = edits | (WIFI_RAW if keys & WIFI_RAW else set())
    for key in raw_updates | filters:
        result.pop(key, None)
        if key in normalized:
            result[key] = deepcopy(normalized[key])
    typed = deepcopy(result.get('__typed_specs', {}))
    for key in keys:
        typed.pop(key, None)
    typed.update(build_typed_specs({key: result[key] for key in keys if key in result}))
    result['__typed_specs'] = typed
    return result


def product_projection(product, row: dict, *, series_ref: str | None = None) -> dict:
    specs = product.specs or {}
    if series_ref is None and product.series_id is not None:
        series_ref = f'id:{product.series_id}'
    if not isinstance(specs, dict) or not isinstance(specs.get('__typed_specs', {}), dict):
        raise RepairBlocked('Product specs and typed specs must be objects')
    fields = {}
    for key in row['before']['fields_sha256']:
        value = series_ref if key == 'series_ref' else getattr(product, key)
        fields[key] = digest(value)
    return {'specs': {key: present(specs, key) for key in row['before']['specs']}, 'typed': {key: present(specs.get('__typed_specs', {}), key) for key in row['before']['typed']}, 'filters': {key: present(specs, key) for key in row['before']['filters']}, 'fields_sha256': fields}


def desired_projection(row: dict) -> dict:
    before = row['before']
    specs = {key: deepcopy(cell['value']) for section in ('specs', 'filters') for key, cell in before[section].items() if cell['present']}
    specs['__typed_specs'] = {key: deepcopy(cell['value']) for key, cell in before['typed'].items() if cell['present']}
    specs = repaired_specs(specs, row)
    fields = dict(before['fields_sha256'])
    fields.update({key: digest(val) for key, val in row.get('fields_set', {}).items()})
    if row.get('series_key') is not None:
        fields['series_ref'] = digest(_series_target(row['series_key']))
    return {'specs': {key: present(specs, key) for key in before['specs']}, 'typed': {key: present(specs.get('__typed_specs', {}), key) for key in before['typed']}, 'filters': {key: present(specs, key) for key in before['filters']}, 'fields_sha256': fields}


def _series_target(value: str) -> str:
    return value if value.startswith('id:') else 'key:' + value.removeprefix('key:')


def _ref(value: dict, new_key: str) -> str:
    return f'id:{value["id"]}' if 'id' in value else 'key:' + value[new_key]


def _new_state(kind, row):
    from models import CatalogDocument, Feature, ProductSeries
    model = {'new_series': ProductSeries, 'new_features': Feature, 'documents': CatalogDocument}[kind]
    values = {**row['identity'], **row['fields_set']}
    obj = model.model_validate(values)
    return {key: val for key, val in obj.model_dump(mode='json').items() if key not in {'id', 'created_at', 'updated_at'}}


def _owned_state(obj):
    return {key: val for key, val in obj.model_dump(mode='json').items() if key not in {'id', 'created_at', 'updated_at'}}


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    validate_manifest(data)
    return data


def _validate_series_features(value) -> None:
    if not isinstance(value, list) or len(value) > 100 or any(not isinstance(item, str) or len(item) > 2000 for item in value):
        raise RepairBlocked('Series legacy features must be a bounded list of strings')


def validate_manifest(m: dict) -> None:
    if m.get('schema_version') != 1 or set(m.get('scope', {}).get('brand_ids', [])) != BRAND_IDS:
        raise RepairBlocked('Only reviewed Biocond brands 1/3/14 and schema1 are allowed')
    for kind, scope in [('products', 'product_ids'), ('series', 'series_ids'), ('brands', 'brand_ids')]:
        ids = [r['identity']['id'] for r in m[kind]]
        if len(ids) != len(set(ids)) or set(ids) != set(m['scope'][scope]):
            raise RepairBlocked(f'Manifest must freeze complete {kind} scope')
    for kind, allowed in [('brands', {'official_url'}), ('series', SERIES_FIELDS)]:
        for row in m[kind]:
            if set(row['fields_set']) - allowed or set(row['fields_set']) - set(row['before_sha256']):
                raise RepairBlocked(f'Unreviewed {kind} field or missing before guard')
            if kind == 'series' and 'features' in row['fields_set']:
                _validate_series_features(row['fields_set']['features'])
            if kind == 'brands' and row['fields_set'] and row['before_sha256'].get('official_url') not in {digest(None), digest('')}:
                raise RepairBlocked('Brand official URL may only fill an empty value')
    reviewed_features = m.get('reviewed_features', [])
    if len({r['identity']['id'] for r in reviewed_features}) != len(reviewed_features):
        raise RepairBlocked('Duplicate reviewed feature copy')
    for row in reviewed_features:
        if (set(row['identity']) != {'id', 'brand_id', 'slug'}
                or row['identity']['brand_id'] not in BRAND_IDS
                or set(row['fields_set']) - REVIEWED_FEATURE_COPY_FIELDS
                or set(row['fields_set']) - set(row['before_sha256'])):
            raise RepairBlocked('Only exact brand feature copy with before guards may change')
    for row in m['products']:
        if set(row['identity']) != {'id', 'brand_id', 'slug', 'title'} or row['identity'].get('brand_id') not in BRAND_IDS:
            raise RepairBlocked('Product requires exact identity within brand scope')
        raw = set(row.get('specs_set', {})) | set(row.get('specs_delete', []))
        keys, filters = spec_families(row)
        if raw - set(row.get('rebuild_typed', [])) or keys - set(SPEC_DEFINITIONS) or raw & {'type', 'indoor_units_count', 'includes_indoor_unit', 'includes_outdoor_unit'}:
            raise RepairBlocked('Unreviewed spec field or missing family rebuild')
        if set(row.get('specs_set', {})) & set(row.get('specs_delete', [])):
            raise RepairBlocked('Conflicting spec edits')
        if set(row.get('fields_set', {})) - PRODUCT_FIELDS:
            raise RepairBlocked('Unreviewed product field')
        if 'series_assignment_source' in row.get('fields_set', {}) and row['fields_set']['series_assignment_source'] != 'manual':
            raise RepairBlocked('Only explicit manual series assignment is allowed')
        before = row['before']
        if row.get('source_before_sha256') != digest(before):
            raise RepairBlocked('Invalid source-before projection hash')
        if not keys <= set(before['specs']) or not keys <= set(before['typed']) or not filters <= set(before['filters']):
            raise RepairBlocked('Every touched raw/typed/filter family needs exact before guards')
        required = set(row.get('fields_set', {})) | {'series_ref'}
        if not required <= set(before['fields_sha256']):
            raise RepairBlocked('Product fields/series identity need before guards')
        if 'capacity_cooling_kw' in raw and 'power_cooling' not in row.get('fields_set', {}):
            raise RepairBlocked('Cooling capacity change requires coherent power_cooling')
        if 'power_cooling' in row.get('fields_set', {}):
            typed = desired_projection(row)['typed'].get('capacity_cooling_kw', {}).get('value', {})
            if typed.get('value') != row['fields_set']['power_cooling']:
                raise RepairBlocked('power_cooling differs from typed cooling capacity')
    for kind, fields in [('new_series', SERIES_FIELDS), ('new_features', FEATURE_FIELDS), ('documents', DOCUMENT_FIELDS)]:
        rows = m.get(kind, [])
        natural = [digest(row['identity']) for row in rows]
        if len(natural) != len(set(natural)) or len(rows) > 100 or (kind != 'documents' and len({r['key'] for r in rows}) != len(rows)):
            raise RepairBlocked('Duplicate or unbounded new records')
        for row in rows:
            if row['before'] != {'present': False} or row['identity'].get('brand_id') not in BRAND_IDS or set(row['fields_set']) - fields:
                raise RepairBlocked('Unreviewed new record')
            expected_identity = {'brand_id', 'url' if kind == 'documents' else 'slug'}
            if set(row['identity']) != expected_identity:
                raise RepairBlocked('New record requires exact natural identity')
            if kind == 'new_features' and (row['fields_set'].get('scope_type') != 'brand' or row['fields_set'].get('is_active') is not True):
                raise RepairBlocked('New feature must be active and brand scoped')
            if kind == 'new_series' and 'features' in row['fields_set']:
                _validate_series_features(row['fields_set']['features'])
            if not row['fields_set'].get('source_url'):
                raise RepairBlocked('New source-reviewed record needs provenance')
    for row in m.get('feature_links', []):
        allowed = LINK_EDITS | ({'is_featured'} if row['kind'] == 'series' else set())
        if row['kind'] not in {'series', 'product'} or set(row['fields_set']) - allowed or row['fields_set'].get('source', 'manual') != 'manual':
            raise RepairBlocked('Unreviewed feature-link mutation')
        if row['fields_set'].get('display_mode') not in {None, 'icon', 'compact', 'detailed'}:
            raise RepairBlocked('Invalid feature display mode')


def build_plan(m: dict, catalog: dict, *, now: datetime | None = None) -> dict:
    """Plan from one complete repeatable-read catalog snapshot (objects, not SQL)."""
    validate_manifest(m)
    operations, observed, statuses = [], [], set()
    indexed = {kind: {obj.id: obj for obj in catalog[kind]} for kind in ('brands', 'products', 'series', 'features', 'categories', 'documents')}
    if set(indexed['brands']) != BRAND_IDS or set(indexed['products']) != set(m['scope']['product_ids']):
        raise RepairBlocked('Extra or missing scoped catalog identities')
    refs = {'series': {}, 'features': {}}
    owned_series_ids = set()

    def compare(kind, ref, actual, before, target, fields):
        observed.append({'kind': kind, 'ref': ref, 'state_sha256': digest(actual)})
        if actual != before and actual != target:
            raise RepairBlocked(f'{kind} {ref}: unknown or partially changed state')
        if before != target:
            statuses.add('before' if actual == before else 'after')
            if actual != target:
                operations.append({'kind': kind, 'ref': ref, 'fields_set': fields, 'before_sha256': digest(before), 'after_sha256': digest(target)})

    for kind in ('new_series', 'new_features', 'documents'):
        source = {'new_series': 'series', 'new_features': 'features', 'documents': 'documents'}[kind]
        for row in m.get(kind, []):
            matches = [obj for obj in catalog[source] if all(getattr(obj, key) == value for key, value in row['identity'].items())]
            if len(matches) > 1:
                raise RepairBlocked('Duplicate natural identity')
            obj = matches[0] if matches else None
            actual = {'present': True, 'value': _owned_state(obj)} if obj else {'present': False}
            target = {'present': True, 'value': _new_state(kind, row)}
            ref = row.get('key', digest(row['identity']))
            compare(kind, ref, actual, row['before'], target, {**row['identity'], **row['fields_set']})
            if kind in ('new_series', 'new_features'):
                refs[source][ref] = obj.id if obj else None
                if obj and kind == 'new_series':
                    owned_series_ids.add(obj.id)
            if kind == 'new_features':
                category = indexed['categories'].get(row['fields_set']['category_id'])
                if not category or category.is_active is not True:
                    raise RepairBlocked('New feature category is missing or inactive')
                collisions = [f for f in catalog['features'] if f.slug == row['identity']['slug']]
                if collisions and (not obj or collisions[0].id != obj.id):
                    raise RepairBlocked('Feature slug belongs to another identity')
    if set(indexed['series']) != set(m['scope']['series_ids']) | owned_series_ids:
        raise RepairBlocked('Extra or missing scoped series identities')

    series_refs = {id: 'key:' + key for key, id in refs['series'].items() if id is not None}
    feature_refs = {id: 'key:' + key for key, id in refs['features'].items() if id is not None}
    for kind in ('brands', 'series'):
        for row in m[kind]:
            obj = indexed[kind].get(row['identity']['id'])
            if obj is None:
                raise RepairBlocked('Missing reviewed row')
            _identity(obj, row['identity'])
            before = row['before_sha256']
            actual = {key: digest(getattr(obj, key)) for key in before}
            target = {**before, **{key: digest(value) for key, value in row['fields_set'].items()}}
            compare(kind, obj.id, actual, before, target, row['fields_set'])
    for row in m.get('reviewed_features', []):
        obj = indexed['features'].get(row['identity']['id'])
        if obj is None or obj.scope_type != 'brand' or obj.is_active is not True:
            raise RepairBlocked('Reviewed copy requires an existing active brand feature')
        _identity(obj, row['identity'])
        before = row['before_sha256']
        actual = {key: digest(getattr(obj, key)) for key in before}
        target = {**before, **{key: digest(value) for key, value in row['fields_set'].items()}}
        compare('features', obj.id, actual, before, target, row['fields_set'])
    for row in m['products']:
        obj = indexed['products'][row['identity']['id']]
        _identity(obj, row['identity'])
        series_ref = series_refs.get(obj.series_id, f'id:{obj.series_id}' if obj.series_id is not None else None)
        actual = product_projection(obj, row, series_ref=series_ref)
        target = desired_projection(row)
        assignment = row.get('series_key')
        if assignment is not None:
            target_ref = _series_target(assignment)
            if target_ref.startswith('id:'):
                series = indexed['series'].get(int(target_ref[3:]))
                if series is None or series.brand_id != obj.brand_id:
                    raise RepairBlocked('Product assignment escapes reviewed brand/series')
            else:
                series_row = next((s for s in m.get('new_series', []) if 'key:' + s['key'] == target_ref), None)
                if series_row is None or series_row['identity']['brand_id'] != obj.brand_id:
                    raise RepairBlocked('Unknown or cross-brand symbolic series')
            if row.get('fields_set', {}).get('series_assignment_source') != 'manual':
                raise RepairBlocked('Changed series assignment must be manual')
        compare('products', obj.id, actual, row['before'], target, row.get('fields_set', {}))
        if operations and operations[-1]['kind'] == 'products' and operations[-1]['ref'] == obj.id:
            operations[-1].update(specs_set=row.get('specs_set', {}), specs_delete=row.get('specs_delete', []), series_key=row.get('series_key'))

    def link_key(link):
        return (link['kind'], link['target'], link['feature'])

    baseline = deepcopy(m['manual_links_before'])
    if len({link_key(link) for link in baseline}) != len(baseline):
        raise RepairBlocked('Duplicate baseline link')
    desired_links = {link_key(link): deepcopy(link) for link in baseline}
    new_link_keys = set()
    seen = set()
    for row in m.get('feature_links', []):
        target, feature = _ref(row['target'], 'series_key'), _ref(row['feature'], 'feature_key')
        key = (row['kind'], target, feature)
        if key in seen:
            raise RepairBlocked('Duplicate feature-link operation')
        seen.add(key)
        if target.startswith('id:'):
            owner = indexed[row['kind'] if row['kind'] == 'series' else 'products'].get(int(target[3:]))
            if owner is None:
                raise RepairBlocked('Feature-link owner escapes scope')
            brand_id = owner.brand_id
        else:
            sr = next((s for s in m.get('new_series', []) if 'key:' + s['key'] == target), None)
            if row['kind'] != 'series' or sr is None:
                raise RepairBlocked('Unknown feature-link owner')
            brand_id = sr['identity']['brand_id']
        if feature.startswith('id:'):
            feat = indexed['features'].get(int(feature[3:]))
            if feat is None or feat.is_active is not True or feat.scope_type == 'derived' or feat.brand_id not in {None, brand_id}:
                raise RepairBlocked('Manual feature must be active, nonderived and brand compatible')
            observed.append({'kind': 'referenced_feature', 'ref': feat.id, 'state_sha256': digest(_owned_state(feat))})
        else:
            feat_row = next((f for f in m.get('new_features', []) if 'key:' + f['key'] == feature), None)
            if feat_row is None or feat_row['identity']['brand_id'] != brand_id:
                raise RepairBlocked('Unknown or cross-brand feature key')
        old = desired_links.get(key)
        before = {'present': True, 'value': old['fields']} if old else {'present': False}
        if before != row['before']:
            raise RepairBlocked('Feature link lacks exact baseline before guard')
        fields = deepcopy(old['fields']) if old else {field: None for field in LINK_FIELDS}
        if old is None:
            fields.update(source='manual', is_enabled=True, sort_order=0)
            if row['kind'] == 'series':
                fields['is_featured'] = False
            new_link_keys.add(key)
        fields.update(row['fields_set'])
        if fields['source'] != 'manual':
            raise RepairBlocked('Changed feature link must be manual')
        desired_links[key] = {'id': old['id'] if old else 'new:' + ':'.join(key), 'kind': row['kind'], 'target': target, 'feature': feature, 'fields': fields}
    actual_links = []
    for kind, obj in catalog['links']:
        target_id = getattr(obj, kind + '_id')
        target = series_refs.get(target_id, f'id:{target_id}') if kind == 'series' else f'id:{target_id}'
        feature = feature_refs.get(obj.feature_id, f'id:{obj.feature_id}')
        item = link_projection(obj, kind, target=target, feature=feature)
        if link_key(item) in new_link_keys:
            item['id'] = 'new:' + ':'.join(link_key(item))
        actual_links.append(item)
    order = lambda rows: sorted(rows, key=lambda item: link_key(item))
    compare('feature_links', 'all_scoped', order(actual_links), order(baseline), order(list(desired_links.values())), {})
    if len(statuses) > 1:
        raise RepairBlocked('Partial repair across scoped rows')
    brand_slugs = sorted(obj.slug for obj in catalog['brands'])
    series_paths = {f'/brands/{quote(indexed["brands"][obj.brand_id].slug, safe="")}/series/{quote(obj.slug, safe="")}/' for obj in catalog['series']}
    for row in m.get('new_series', []):
        series_paths.add(f'/brands/{quote(indexed["brands"][row["identity"]["brand_id"]].slug, safe="")}/series/{quote(row["identity"]["slug"], safe="")}/')
    payload = {'ready': True, 'manifest_sha256': digest(m), 'sources': m['sources'], 'observed': observed, 'operations': operations, 'changed': len(operations), 'product_ids': sorted(indexed['products']), 'brand_slugs': brand_slugs, 'series_paths': sorted(series_paths)}
    payload['state_digest'] = digest(payload)
    now = now or datetime.now(timezone.utc)
    payload.update(created_at=now.isoformat(), expires_at=(now + timedelta(minutes=30)).isoformat())
    payload['plan_digest'] = digest(payload)
    return payload


def validate_reviewed_plan(reviewed: dict, live: dict, supplied_digest: str, *, now=None) -> None:
    now = now or datetime.now(timezone.utc)
    if reviewed.get('plan_digest') != supplied_digest or digest({k: v for k, v in reviewed.items() if k != 'plan_digest'}) != supplied_digest:
        raise RepairBlocked('Reviewed plan digest is invalid')
    try:
        created, expires = (datetime.fromisoformat(reviewed[key]) for key in ('created_at', 'expires_at'))
        valid = created <= now < expires and expires - created == timedelta(minutes=30)
    except (ValueError, TypeError, KeyError):
        valid = False
    if not valid:
        raise RepairBlocked('Reviewed plan expired or invalid validity window')
    if reviewed.get('manifest_sha256') != live['manifest_sha256'] or reviewed.get('state_digest') != live['state_digest']:
        raise RepairBlocked('Manifest or scoped catalog state changed since review')
