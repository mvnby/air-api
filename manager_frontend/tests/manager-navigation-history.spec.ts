import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { navigateManager, openManagerChild, replaceManagerLocation, returnToManager, startManagerNavigation } from '../src/services/manager-navigation-history';
import { normalizeOrderLocation, openOrderPage, returnFromOrder } from '../src/services/order-navigation';
import { registerUnsavedNavigationGuard } from '../src/services/unsaved-navigation-guard';

const board = '/manager/orders/kanban?segment=b2b&groupBy=none&search=office';
const location = () => window.location.pathname + window.location.search;
let stop: () => void;
let unregister: (() => void) | undefined;
const accepted = vi.fn();
beforeEach(() => {
  window.history.replaceState({}, '', board);
  accepted.mockClear();
  stop = startManagerNavigation(accepted, normalizeOrderLocation);
});
afterEach(() => { unregister?.(); unregister = undefined; stop(); });

describe('guarded Manager history', () => {
  it('does not add a canceled customer transition to Back or Forward history', async () => {
    await openOrderPage(477);
    const order = location(), length = history.length;
    unregister = registerUnsavedNavigationGuard(() => false);
    expect(await openManagerChild('/manager/customers/profile?customerId=12')).toBe(false);
    expect(location()).toBe(order);
    expect(history.length).toBe(length);
    unregister();
    history.back();
    await vi.waitFor(() => expect(location()).toBe(board));
    history.forward();
    await vi.waitFor(() => expect(location()).toBe(order));
  });

  it('restores a canceled native traversal without adding an entry or losing Forward', async () => {
    await openOrderPage(477);
    const order = location(), length = history.length;
    const guard = vi.fn(() => false);
    unregister = registerUnsavedNavigationGuard(guard);
    history.back();
    await vi.waitFor(() => { expect(guard).toHaveBeenCalledOnce(); expect(location()).toBe(order); });
    expect(history.length).toBe(length);
    unregister();
    history.back();
    await vi.waitFor(() => expect(location()).toBe(board));
    history.forward();
    await vi.waitFor(() => expect(location()).toBe(order));
  });

  it.each(['customer', 'catalog'])('returns via %s to the original order and board entries', async child => {
    const boardState = { expandedOrderId: 477, expandedGroupIds: ['12'], columnFilters: { negotiation: 'awaiting_offer' }, scrollLeft: 160 };
    await openOrderPage(477, boardState);
    replaceManagerLocation(`${location()}&section=documents`);
    const order = location();
    const orderEntry = history.state.managerNavigation.id;
    await openManagerChild(child === 'customer' ? '/manager/customers/profile?customerId=12' : '/manager/catalog-decision?orderId=477&proposalId=25');
    const target = child === 'catalog' ? `${order}&proposalId=25` : order;
    returnToManager(target);
    await vi.waitFor(() => { expect(location()).toBe(target); expect(history.state.managerNavigation.id).toBe(orderEntry); });
    returnFromOrder(board);
    await vi.waitFor(() => expect(location()).toBe(board));
    expect(history.state.orderListPosition.board).toEqual(boardState);
  });

  it('preserves calendar date and view through a child page and order return', async () => {
    window.history.replaceState({ ...history.state, orderCalendar: { date: '2026-12-14', view: 'timeGridWeek' } }, '', '/manager/calendar');
    await openOrderPage(477);
    const order = location();
    await openManagerChild('/manager/customers/profile?customerId=12');
    returnToManager(order);
    await vi.waitFor(() => expect(location()).toBe(order));
    returnFromOrder('/manager/calendar');
    await vi.waitFor(() => expect(location()).toBe('/manager/calendar'));
    expect(history.state.orderCalendar).toEqual({ date: '2026-12-14', view: 'timeGridWeek' });
  });

  it('keeps a direct link in place when its save barrier fails', async () => {
    await navigateManager('/manager/orders/477');
    unregister = registerUnsavedNavigationGuard(() => false);
    expect(await returnFromOrder(board)).toBe(false);
    expect(location()).toBe('/manager/orders/477');
  });
});
