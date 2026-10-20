import { afterEach, describe, expect, it, vi } from 'vitest';
import { normalizeOrderLocation, openOrderPage, orderPageUrl, orderReturnUrl, readOrderPage, returnFromOrder, savedOrderListPosition } from '../src/services/order-navigation';

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
  it('retains all filters and board position in the history entry being left', () => {
    const url = '/manager/orders/kanban?segment=b2b&assigned_to_me=1&workFilter=unpaid&hideOnHold=false&status=execution&sort=margin_desc&groupBy=none&search=office';
    window.history.replaceState({ other: 'preserved' }, '', url);
    const replace = vi.spyOn(window.history, 'replaceState');
    openOrderPage(477, { expandedOrderId: 12, expandedGroupIds: ['42'], columnFilters: { execution: 'needs_schedule' }, scrollLeft: 640 });
    const saved = replace.mock.calls[0]![0];
    expect(saved.other).toBe('preserved');
    expect(saved.orderListPosition).toMatchObject({ url, board: { scrollLeft: 640, expandedGroupIds: ['42'] } });
    expect(readOrderPage(`${window.location.pathname}${window.location.search}`)).toEqual({ orderId: 477, returnTo: url });
    const back = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    returnFromOrder(url);
    expect(back).toHaveBeenCalledOnce();
    window.history.replaceState(saved, '', url);
    expect(savedOrderListPosition()).toEqual(saved.orderListPosition);
  });
  it('returns a direct order link to a safe board URL without a back-navigation loop', () => {
    window.history.replaceState({}, '', orderPageUrl(477));
    returnFromOrder('/manager/orders/list?segment=b2b');
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
