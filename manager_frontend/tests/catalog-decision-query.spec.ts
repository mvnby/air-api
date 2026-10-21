import { readCatalogDecisionContext } from '../src/services/catalog-decision-context';
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
    expect(state).toEqual({ filters: { isPublished: true, coolingBtuClasses: [30] }, page: 1, sort: 'recommended', direction: 'asc' });
  });
  it('defaults to all forms with wall-first ordering and clears its irrelevant descending direction', () => {
    expect(readCatalogDecisionQuery('?direction=desc')).toEqual({ filters: { isPublished: true }, page: 1, sort: 'recommended', direction: 'asc' });
    expect(readCatalogDecisionQuery('?sort=recommended&direction=desc').direction).toBe('asc');
    expect(writeCatalogDecisionQuery('?sort=title&direction=desc&orderId=42', {
      filters: { isPublished: true }, page: 1, sort: 'recommended', direction: 'desc',
    })).toBe('?orderId=42');
  });
  it.each(['title', 'retail_price', 'cooling_power'] as const)('retains explicit %s sorting in bookmarks', sort => {
    const state = { filters: { isPublished: true }, sort, direction: 'desc' as const, page: 1 };
    const query = writeCatalogDecisionQuery('', state);
    expect(new URLSearchParams(query).get('sort')).toBe(sort);
    expect(readCatalogDecisionQuery(query)).toEqual(state);
  });
  it('removes dependent series when removing a selected brand', () => {
    const filters = { brandIds: [1, 2], seriesIds: [11, 22], isPublished: true };
    const chips = catalogDecisionChips(filters, [{ id: 1, title: 'Gree' }], [{ id: 11, title: 'Amber', brandId: 1 }, { id: 22, title: 'Flexis', brandId: 2 }]);
    expect(chips.find(item => item.key === 'brandIds-1')?.remove()).toEqual({ brandIds: [2], seriesIds: [22], isPublished: true });
  });
});


it('returns catalog selections to the standalone order and preserves its board URL', () => {
  const search = new URLSearchParams({ orderId: '477', proposalId: '25', returnTo: '/manager/orders/477?returnTo=%2Fmanager%2Forders%2Fkanban%3Fsegment%3Db2b' });
  const context = readCatalogDecisionContext(`?${search}`)!;
  expect(context.returnTo).toBe('/manager/orders/477?returnTo=%2Fmanager%2Forders%2Fkanban%3Fsegment%3Db2b&proposalId=25');
});
