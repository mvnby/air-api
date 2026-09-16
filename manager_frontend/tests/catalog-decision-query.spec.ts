import { describe, expect, it } from 'vitest';
import { catalogDecisionChips, readCatalogDecisionQuery, writeCatalogDecisionQuery } from '../src/services/catalog-decision-query';

describe('catalog query navigation', () => {
  it('round trips filters and pagination without losing exact proposal navigation', () => {
    const original = '?orderId=42&proposalId=51&returnTo=%2Fmanager%2Forders%3Fview%3Dlist';
    const state = { filters: { isPublished: true, coolingBtuClasses: [12, 30], brandIds: [1], seriesIds: [8], retailMinByn: 0, retailMaxByn: 3000, wifi: 'builtin' as const, includeOrderable: true }, sort: 'retail_price' as const, direction: 'desc' as const, page: 3 };
    const query = writeCatalogDecisionQuery(original, state);
    expect(readCatalogDecisionQuery(query)).toEqual(state);
    expect(new URLSearchParams(query).get('proposalId')).toBe('51');
    expect(new URLSearchParams(query).get('returnTo')).toBe('/manager/orders?view=list');
  });
  it('rejects malformed or unsupported URL criteria', () => {
    const state = readCatalogDecisionQuery('?page=-9&coolingBtuClasses=0,30,30,99&retailMinByn=Infinity&coolingMinKw=10&coolingMaxKw=2&form=unknown&wifi=unknown&sort=secret&seriesIds=8');
    expect(state).toEqual({ filters: { isPublished: true, coolingBtuClasses: [30] }, page: 1, sort: 'title', direction: 'asc' });
  });
  it('removes dependent series when removing a selected brand', () => {
    const filters = { brandIds: [1, 2], seriesIds: [11, 22], isPublished: true };
    const chips = catalogDecisionChips(filters, [{ id: 1, title: 'Gree' }], [{ id: 11, title: 'Amber', brandId: 1 }, { id: 22, title: 'Flexis', brandId: 2 }]);
    expect(chips.find(item => item.key === 'brandIds-1')?.remove()).toEqual({ brandIds: [2], seriesIds: [22], isPublished: true });
  });
});
