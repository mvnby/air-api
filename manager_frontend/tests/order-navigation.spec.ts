import { effectScope, ref } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { normalizeOrderLocation, openOrderPage, orderPageUrl, orderReturnUrl, readOrderPage, returnFromOrder, savedOrderListPosition, readOrderWorkspaceSection } from '../src/services/order-navigation';

import { useManagerDocumentTitle } from '../src/services/manager-document-title';

afterEach(() => { vi.restoreAllMocks(); window.history.replaceState({}, '', '/manager/orders'); });
describe('order page navigation', () => {
  it.each(['/manager/orders', '/manager/orders/kanban', '/manager/orders/list'])('keeps legacy %s links and proposal context without loading the board', path => {
    window.history.replaceState({}, '', `${path}?segment=b2b&search=office&groupBy=customer&orderId=477&proposalId=25`);
    const location = normalizeOrderLocation();
    const route = readOrderPage(location)!;
    expect(route.orderId).toBe(477);
    expect(new URLSearchParams(window.location.search).get('proposalId')).toBe('25');
    expect(route.returnTo).toBe(`${path}?segment=b2b&search=office&groupBy=customer`);
    expect(normalizeOrderLocation()).toBe(location);
  });
  it('preserves explicit company and site context before authentication bootstrap', () => {
    window.history.replaceState({}, '', '/manager/orders/kanban?company=42&site=minsk&orderId=477');
    normalizeOrderLocation();
    const query = new URLSearchParams(window.location.search);
    expect(query.get('company')).toBe('42');
    expect(query.get('site')).toBe('minsk');
    expect(readOrderPage(window.location.href)?.returnTo).toContain('company=42&site=minsk');
    window.history.replaceState({}, '', '/manager/orders?company=42&company=99&orderId=477');
    normalizeOrderLocation();
    expect(new URLSearchParams(window.location.search).getAll('company')).toEqual(['42', '99']);
  });
  it('retains all filters and board position in the history entry being left', async () => {
    const url = '/manager/orders/kanban?segment=b2b&assigned_to_me=1&workFilter=unpaid&hideOnHold=false&status=execution&sort=margin_desc&groupBy=none&search=office';
    window.history.replaceState({ other: 'preserved' }, '', url);
    const replace = vi.spyOn(window.history, 'replaceState');
    await openOrderPage(477, { expandedOrderId: 12, expandedGroupIds: ['42'], columnFilters: { execution: 'needs_schedule' }, scrollLeft: 640 });
    const saved = replace.mock.calls[0]![0];
    expect(saved.other).toBe('preserved');
    expect(saved.orderListPosition).toMatchObject({ url, board: { scrollLeft: 640, expandedGroupIds: ['42'] } });
    expect(readOrderPage(`${window.location.pathname}${window.location.search}`)).toEqual({ orderId: 477, returnTo: url });
    const back = vi.spyOn(window.history, 'go').mockImplementation(() => {});
    returnFromOrder(url);
    expect(back).toHaveBeenCalledExactlyOnceWith(-1);
    window.history.replaceState(saved, '', url);
    expect(savedOrderListPosition()).toEqual(saved.orderListPosition);
  });
  it('returns a direct order link to a safe board URL without a back-navigation loop', async () => {
    window.history.replaceState({}, '', orderPageUrl(477));
    await returnFromOrder('/manager/orders/list?segment=b2b');
    expect(window.location.pathname + window.location.search).toBe('/manager/orders/list?segment=b2b');
  });
  it.each(['https://example.com/manager/orders', '//example.com', 'http://[bad', '/manager/orders/477', '/manager/profile'])('rejects an unsuitable return URL: %s', value => {
    expect(orderReturnUrl(value)).toBe('/manager/orders/kanban');
  });
  it.each(['0', '-1', '12oops', '9007199254740992'])('does not interpret invalid order IDs as routes: %s', value => {
    window.history.replaceState({}, '', `/manager/orders?orderId=${value}`);
    expect(normalizeOrderLocation()).toBe(`/manager/orders?orderId=${value}`);
    expect(readOrderPage(`/manager/orders/${value}`)).toBeNull();
  });
});


describe('order section links', () => {
  it('keeps an explicit return route and independent bootstrap context on legacy links', () => {
    const params = new URLSearchParams({ orderId: '477', proposalId: '25', section: 'documents', returnTo: '/manager/calendar?view=week', company: '42', site: 'minsk' });
    window.history.replaceState({}, '', `/manager/orders?${params}`);
    const canonical = normalizeOrderLocation();
    expect(readOrderPage(canonical)?.returnTo).toBe('/manager/calendar?view=week');
    const query = new URLSearchParams(window.location.search);
    for (const key of ['proposalId', 'section', 'company', 'site']) expect(query.get(key)).toBe(params.get(key));
  });

  it.each(['proposal', 'documents', 'work', 'payments'] as const)('retains %s when normalizing a legacy link and building a canonical link', section => {
    window.history.replaceState({}, '', `/manager/orders/list?orderId=477&section=${section}&proposalId=25&company=42&site=minsk&search=office`);
    const canonical = normalizeOrderLocation();
    expect(readOrderWorkspaceSection(canonical)).toBe(section);
    expect(new URLSearchParams(window.location.search).get('proposalId')).toBe('25');
    expect(new URLSearchParams(window.location.search).get('company')).toBe('42');
    expect(new URLSearchParams(window.location.search).get('site')).toBe('minsk');
    expect(readOrderPage(canonical)?.returnTo).toBe('/manager/orders/list?company=42&site=minsk&search=office');
    expect(normalizeOrderLocation()).toBe(canonical);
    expect(readOrderWorkspaceSection(orderPageUrl(477, '/manager/orders/list', '25', section))).toBe(section);
  });
});

describe('coordinated Manager document title', () => {
  it('keeps the order title through late identity updates and restores identity when leaving', () => {
    const identity = ref<string | null>('MVN');
    const identityScope = effectScope();
    identityScope.run(() => useManagerDocumentTitle(identity, 'identity'));
    expect(document.title).toBe('MVN · KitLane');
    const page = ref('Заказ №477');
    const pageScope = effectScope();
    pageScope.run(() => useManagerDocumentTitle(page));
    expect(document.title).toBe('Заказ №477 · KitLane');
    page.value = 'Заказ №477 · Клиент';
    identity.value = 'Другой бренд';
    expect(document.title).toBe('Заказ №477 · Клиент · KitLane');
    identity.value = null;
    expect(document.title).toBe('Заказ №477 · Клиент · KitLane');
    identity.value = 'MVN';
    pageScope.stop();
    expect(document.title).toBe('MVN · KitLane');
    identityScope.stop();
    expect(document.title).toBe('KitLane');
  });

  it('does not restore a disposed page over its replacement', () => {
    const first = effectScope(), second = effectScope();
    first.run(() => useManagerDocumentTitle(ref('Заказ №477')));
    second.run(() => useManagerDocumentTitle(ref('Заказ №478')));
    first.stop();
    expect(document.title).toBe('Заказ №478 · KitLane');
    second.stop();
    expect(document.title).toBe('KitLane');
  });
});
