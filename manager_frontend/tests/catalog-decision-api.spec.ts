import { afterEach, describe, expect, it, vi } from 'vitest';
import { catalogDecisionApi } from '../src/services/catalog-decision-api';

afterEach(() => vi.unstubAllGlobals());

describe('catalog decision HTTP filters', () => {
  it('sends the explicit all-stock flag, exact selection and budget through the generated client', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], meta: { page: 1, pages: 0, total: 0, limit: 24 } }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetch);
    await catalogDecisionApi.list(1, 24, { includeOrderable: true, isPublished: true, productIds: [11, 22], retailMinByn: 0, retailMaxByn: 3000, wifi: 'builtin', coolingBtuClasses: [30] }, 'retail_price', 'asc');
    const url = new URL(String(fetch.mock.calls[0]?.[0]), 'https://manager.test');
    expect(url.pathname).toBe('/api/manager/catalog-decision/products');
    expect(url.searchParams.get('include_orderable')).toBe('true');
    expect(url.searchParams.get('retail_min_byn')).toBe('0');
    expect(url.searchParams.get('retail_max_byn')).toBe('3000');
    expect(url.searchParams.getAll('product_ids')).toEqual(['11', '22']);
    expect(url.searchParams.get('cooling_btu_classes')).toBe('30');
    expect(url.searchParams.get('wifi')).toBe('builtin');
    expect(url.searchParams.get('is_published')).toBe('true');
  });
});
