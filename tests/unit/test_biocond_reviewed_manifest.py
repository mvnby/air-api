"""The reviewed source decisions must stay coherent across raw and typed data."""
from services.catalog_biocond_source_repair import load_manifest, repaired_specs


def original_specs(row):
    before = row['before']
    result = {
        key: cell['value']
        for section in ('specs', 'filters')
        for key, cell in before[section].items()
        if cell['present']
    }
    result['__typed_specs'] = {
        key: cell['value'] for key, cell in before['typed'].items()
        if cell['present']
    }
    return result


def test_reviewed_model_decisions_rebuild_coherent_values_without_global_inference():
    manifest = load_manifest()
    rows = {row['identity']['id']: row for row in manifest['products']}
    assert len(rows) == 351
    assert len(manifest['scope']['series_ids']) == 64
    for product_id, cooling, heating in (
        (119, 2.62, 2.70), (120, 3.40, 3.42),
        (121, 5.14, 5.21), (122, 7.04, 7.20),
        (1242, 2.64, 3.15), (1243, 3.52, 3.76),
    ):
        row = rows[product_id]
        updated = repaired_specs(original_specs(row), row)
        assert updated['__typed_specs']['capacity_heating_kw']['value'] == heating
        # Unchanged cooling is intentionally absent from some guarded families.
        if 'capacity_cooling_kw' in row['specs_set']:
            assert row['fields_set']['power_cooling'] == cooling
            assert updated['__typed_specs']['capacity_cooling_kw']['value'] == cooling
    assert rows[779]['specs_set']['capacity_heating_kw'] == '3.0'
    for product_id in (779, 783, 784, 785, 786, 1238, 1239, 1240, 1241, 1242, 1243):
        assert 'temp_range_heat' not in rows[product_id]['specs_set']


def test_supplier_wifi_stays_product_scoped_and_component_power_is_not_guessed():
    manifest = load_manifest()
    rows = {row['identity']['id']: row for row in manifest['products']}
    updated = repaired_specs(original_specs(rows[33]), rows[33])
    assert updated['wifi_state'] == 'builtin'
    assert updated['wifi_builtin'] is True
    assert updated['__filter_wifi_builtin'] is True
    assert updated['pipe_liquid'] == '1/4"'
    assert updated['pipe_gas'] == '3/8"'
    for product_id in (49, 142, 877, 878, 1015):
        assert 'wifi_state' not in rows[product_id]['specs_set']
    for product_id in (866, 1037, 1038, 1039, 1040, 1041, 1055, 1056):
        row = rows[product_id]
        updated = repaired_specs(original_specs(row), row)
        for key in ('power_cons_cooling_kw', 'power_cons_heating_kw'):
            assert key not in updated
            assert key not in updated['__typed_specs']
    assert all(
        row['feature'].get('id') not in {40, 73, 74, 75, 81, 84}
        for row in manifest['feature_links']
    )
    assert all(
        row['feature']['feature_key'] != 'mhi-clean-air-filters'
        or row['target'] != {'series_key': 'mhi-srk-ztl-w'}
        for row in manifest['feature_links'] if 'feature_key' in row['feature']
    )
