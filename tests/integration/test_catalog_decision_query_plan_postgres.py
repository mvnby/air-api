"""Prevent repeated JSON-to-JSONB conversion in catalog list/count/facet plans."""
import pytest
from models import Product
from models.tenancy import TenantScope
from services.catalog_decision_projection import CatalogDecisionFilters, CatalogDecisionQueryService


def _nodes(plan):
    yield plan
    for child in plan.get('Plans', []):
        yield from _nodes(child)


@pytest.mark.asyncio
async def test_list_count_and_facets_materialize_large_specs_once(db, monkeypatch):
    # Imported cards retain many typed/source fields. A tiny fixture without
    # these fields cannot expose the repeated document conversion regression.
    details = {f'source_field_{i}': {'raw': f'Original source value {i}', 'value': i} for i in range(180)}
    products = [Product(title=f'Plan wall {i}', slug=f'plan-wall-{i}', price=2000,
                        power_cooling=7, is_published=True, product_kind='complete_split_system',
                        specs={'type': 'сплит-система', 'indoor_type': 'настенный',
                               'capacity_cooling_kw': '7', 'area_m2': '70', '__typed_specs': details})
                for i in range(12)]
    db.add_all(products)
    await db.commit()
    original = db.execute
    statements = []

    async def record(statement, *args, **kwargs):
        if 'jsonb_extract_path_text' in str(statement):
            statements.append(statement)
        return await original(statement, *args, **kwargs)

    monkeypatch.setattr(db, 'execute', record)
    result = await CatalogDecisionQueryService.list_products(
        db, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
        filters=CatalogDecisionFilters(cooling_btu_classes=(24,), indoor_form_factor='wall'),
        page=1, limit=5, sort='cooling_power', direction='asc',
    )
    assert result['meta']['total'] == 12
    assert [r['id'] for r in result['items']] == [p.id for p in products[:5]]
    await CatalogDecisionQueryService.list_filter_options(
        db, tenant_scope=TenantScope(tenant_id=1, storefront_id=1, is_system=True),
    )
    assert len(statements) == 4  # page, count, brands, series
    conn = await db.connection()
    for statement in statements:
        compiled = statement.compile(dialect=db.bind.dialect, compile_kwargs={'render_postcompile': True})
        plan = (await conn.exec_driver_sql(
            'EXPLAIN (ANALYZE, VERBOSE, FORMAT JSON) ' + str(compiled),
            tuple(compiled.params[k] for k in compiled.positiontup),
        )).scalar_one()[0]['Plan']
        conversions = [n for n in _nodes(plan) if n.get('Subplan Name') == 'CTE catalog_decision_specs']
        assert len(conversions) == 1
        assert conversions[0]['Actual Loops'] <= 1
        assert conversions[0]['Actual Rows'] <= len(products)
        # The raw JSON column is converted at the materialization boundary,
        # never repeatedly inside the outer numeric/filter expressions.
        assert str(compiled).count('CAST(product.specs AS JSONB)') == 1


@pytest.mark.asyncio
async def test_editing_catalog_reuses_specs_without_excluding_components(db):
    from api_contracts.catalog_management import CatalogManagementFilters
    from crud.catalog_management import CatalogManagementDAO
    products = [Product(title=f"Management {kind}", slug=f"management-{kind}", price=2000,
                        power_cooling=7, product_kind=kind,
                        specs={"indoor_type": "настенный", "capacity_cooling_kw": "7"})
                for kind in ("complete_split_system", "indoor_unit", "other")]
    db.add_all(products)
    await db.commit()
    statement = CatalogManagementDAO.selection(db, CatalogManagementFilters(cooling_btu_classes=[24], indoor_form_factor="wall"))
    assert set((await db.execute(statement)).scalars()) == {p.id for p in products}
    compiled = str(statement.compile(dialect=db.bind.dialect))
    assert compiled.count("CAST(product.specs AS JSONB)") == 1
    assert "AS MATERIALIZED" in compiled
    # A catalog request without technical filters does not need JSON parsing.
    plain = CatalogManagementDAO.selection(db, CatalogManagementFilters())
    assert "catalog_decision_specs" not in str(plain)
