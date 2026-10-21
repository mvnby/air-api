import { nextTick } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
import { api } from '../src/api';
import type { ManagerOrderListItemResponse } from '../src/client';
import OrdersDashboard from '../src/components/orders/OrdersDashboard.vue';
import { useOrdersDashboardModel } from '../src/components/orders/useOrdersDashboardModel';
import { matchesOrderWorkFilter } from '../src/components/orders/order-work-filters';

const order = (id: number, overrides: Partial<ManagerOrderListItemResponse> = {}) => ({
  id, status: 'negotiation', title: `Заказ ${id}`, created_at: '2026-09-01',
  total_amount: 100, total_cost: 0, margin: 100, balance_due: 100,
  customer: { id: 1, name: 'Клиент', type: 'company' },
  ...overrides,
}) as ManagerOrderListItemResponse;
const response = (items: ManagerOrderListItemResponse[], pages = 1) => ({
  items, meta: { page: 1, limit: 100, total: items.length, pages },
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
let wrapper: VueWrapper | undefined;
beforeEach(() => {
  localStorage.clear();
  window.history.replaceState({}, '', '/manager/orders/kanban?segment=b2b');
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-09-13T12:00:00Z'));
});
afterEach(() => {
  wrapper?.unmount();
  wrapper = undefined;
  vi.restoreAllMocks();
  vi.useRealTimers();
});
const mountDashboard = () => mount(OrdersDashboard, {
  global: { stubs: { OrderEditDrawer: true, OrdersImportPreviewModal: true, OrderKanbanBoard: true, OrdersListTable: true } },
});

describe('work filters', () => {
  it('separates a missed contact from a payment balance and ignores closed contacts', () => {
    const past = '2026-09-12T12:00:00Z';
    expect(matchesOrderWorkFilter(order(1, { next_followup_date: past }), 'followup')).toBe(true);
    expect(matchesOrderWorkFilter(order(2), 'followup')).toBe(false);
    expect(matchesOrderWorkFilter(order(3, { status: 'closed', next_followup_date: past }), 'followup')).toBe(false);
    expect(matchesOrderWorkFilter(order(4, { status: 'closed', closing_result: 'lost', balance_due: 25 }), 'unpaid')).toBe(true);
    expect(matchesOrderWorkFilter(order(5, { balance_due: 0 }), 'unpaid')).toBe(false);
  });

  it('shows approved negotiations and unscheduled execution, not work already scheduled or finished', () => {
    expect(matchesOrderWorkFilter(order(1, { ready_for_execution: true }), 'planning')).toBe(true);
    expect(matchesOrderWorkFilter(order(2, { ready_for_execution: false }), 'planning')).toBe(false);
    expect(matchesOrderWorkFilter(order(3, { status: 'execution', execution_status: 'needs_schedule' }), 'planning')).toBe(true);
    expect(matchesOrderWorkFilter(order(4, { status: 'execution', execution_status: 'scheduled', ready_for_execution: true }), 'planning')).toBe(false);
    expect(matchesOrderWorkFilter(order(5, { status: 'closed', ready_for_execution: true }), 'planning')).toBe(false);
  });

  it('filters before customer grouping so counts, groups and selection contain the same orders', () => {
    const model = useOrdersDashboardModel(vi.fn());
    model.orders.value = [order(1), order(2, { balance_due: 0 }), order(3, { is_on_hold: true })];
    model.workFilter.value = 'unpaid';
    expect(model.visibleOrderIds.value).toEqual([1]);
    expect(model.listItems.value).toHaveLength(1);
    expect(model.listItems.value[0]?.type).toBe('order');
    expect(model.workFilterCounts.value.unpaid).toBe(1);
    expect(model.hiddenOnHoldCount.value).toBe(1);
    model.selectAllVisible();
    expect(model.selectedOrderIds.value).toEqual([1]);
  });
});

describe('dashboard search and completeness', () => {
  it('renders loaded filter counts before restoring the list position', async () => {
    const url = '/manager/orders/kanban?segment=b2b';
    window.history.replaceState({}, '', url);
    const loaded = deferred<ReturnType<typeof response>>();
    vi.spyOn(api, 'getManagerOrders').mockReturnValue(loaded.promise);
    const scroll = vi.spyOn(window, 'scrollTo').mockImplementation(() => {
      expect(wrapper!.text()).toContain('По фильтрам: 1');
      expect(wrapper!.text()).not.toContain('Загрузка заказов…');
    });
    wrapper = mountDashboard(); await flushPromises();
    window.history.replaceState({ orderListPosition: { url: window.location.pathname + window.location.search, top: 500 } }, '');
    loaded.resolve(response([order(1)])); await flushPromises();
    expect(scroll).toHaveBeenCalledExactlyOnceWith(0, 500);
  });
  it('keeps the exact customer filter on every page and explicitly clears it', async () => {
    window.history.replaceState({}, '', '/manager/orders/kanban?segment=all&customerId=42');
    const getOrders = vi.spyOn(api, 'getManagerOrders').mockResolvedValue(response([order(1)], 2));
    wrapper = mountDashboard();
    await flushPromises();
    expect(getOrders).toHaveBeenCalledTimes(2);
    for (const [params] of getOrders.mock.calls) expect(params.customerId).toBe(42);
    expect(wrapper.find('a[href="/manager/customers/profile?customerId=42"]').exists()).toBe(true);
    await wrapper.findAll('button').find(button => button.text() === 'Все клиенты')!.trigger('click');
    await flushPromises();
    expect(getOrders).toHaveBeenLastCalledWith(expect.objectContaining({ customerId: undefined }));
    expect(window.location.search).not.toContain('customerId');
  });
  it('shows a retryable load error instead of presenting old rows as a successful empty result', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(api, 'getManagerOrders')
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(response([order(1)]));
    wrapper = mountDashboard();
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось загрузить заказы');
    expect(wrapper.text()).not.toContain('По фильтрам: 0');
    await wrapper.get('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('По фильтрам: 1');
  });

  it('loads all API pages and exposes then resets the default hidden on-hold filter', async () => {
    const getOrders = vi.spyOn(api, 'getManagerOrders')
      .mockResolvedValueOnce(response([order(1)], 2))
      .mockResolvedValueOnce(response([order(2, { is_on_hold: true })]));
    wrapper = mountDashboard();
    await flushPromises();
    expect(getOrders).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('Отложенные скрыты: 1');
    expect(wrapper.text()).toContain('По фильтрам: 1');
    const reset = wrapper.findAll('button').find((button) => button.text().includes('Сбросить фильтры'))!;
    await reset.trigger('click');
    expect(wrapper.text()).toContain('По фильтрам: 2');
    expect(wrapper.text()).not.toContain('Отложенные скрыты');
  });

  it('does not apply a stale search response while the replacement query is debouncing', async () => {
    const oldSearch = deferred<ReturnType<typeof response>>();
    vi.spyOn(api, 'getManagerOrders')
      .mockResolvedValueOnce(response([order(1)]))
      .mockReturnValueOnce(oldSearch.promise)
      .mockResolvedValueOnce(response([order(9)]));
    wrapper = mountDashboard();
    await flushPromises();
    const search = wrapper.get('input[aria-label="Поиск заказов"]');
    await search.setValue('старый запрос');
    await vi.advanceTimersByTimeAsync(250);
    await search.setValue('новый запрос');
    oldSearch.resolve(response([order(2), order(3)]));
    await flushPromises();
    const board = wrapper.findComponent({ name: 'OrderKanbanBoard' });
    expect(JSON.stringify(board.props('groupedItems'))).not.toContain('Заказ 2');
    await vi.advanceTimersByTimeAsync(250);
    await flushPromises();
    expect(JSON.stringify(board.props('groupedItems'))).toContain('Заказ 9');
  });
});


describe('My orders server filter', () => {
  beforeEach(() => { managerSession.auth.value = { staff_user_id: 7, tenant_id: 2, username: 'maria' } as any; managerStorefrontSelection.selectedSlug.value = 'main'; });
  afterEach(() => { managerSession.auth.value = null; managerStorefrontSelection.selectedSlug.value = null; });
  it('reloads from page one, sends Mine on every page and preserves the other filters and URL parameters', async () => {
    window.history.replaceState({}, '', '/manager/orders/kanban?segment=b2b&customerId=42&search=офис&keep=yes');
    const getOrders = vi.spyOn(api, 'getManagerOrders').mockResolvedValue(response([order(1)], 2));
    wrapper = mountDashboard(); await flushPromises(); getOrders.mockClear();
    const mine = wrapper.get('button[title="Показать заказы, где вы назначены ответственным"]'); await mine.trigger('click'); await flushPromises();
    expect(mine.attributes('aria-pressed')).toBe('true'); expect(getOrders.mock.calls.map(([params]) => params.page)).toEqual([1, 2]);
    for (const [params] of getOrders.mock.calls) expect(params).toEqual(expect.objectContaining({ assignedToMe: true, customerId: 42, segment: 'b2b', search: 'офис' }));
    expect(window.location.search).toContain('assigned_to_me=1'); expect(window.location.search).toContain('keep=yes');
    await wrapper.findAll('button').find(button => button.text().includes('Сбросить фильтры'))!.trigger('click'); await flushPromises(); expect(getOrders).toHaveBeenLastCalledWith(expect.objectContaining({ assignedToMe: false, page: 2 })); expect(window.location.search).not.toContain('assigned_to_me');
  });
  it('restores Mine from the URL and ignores a late previous-filter response including its page count', async () => {
    const old = deferred<ReturnType<typeof response>>();
    const getOrders = vi.spyOn(api, 'getManagerOrders').mockReturnValueOnce(old.promise).mockResolvedValue(response([order(9)]));
    window.history.replaceState({}, '', '/manager/orders/kanban?assigned_to_me=1&segment=b2b'); wrapper = mountDashboard(); await flushPromises();
    expect(getOrders).toHaveBeenCalledWith(expect.objectContaining({ assignedToMe: true }));
    const mine = wrapper.get('button[title="Показать заказы, где вы назначены ответственным"]'); await mine.trigger('click'); await flushPromises();
    old.resolve(response([order(4)], 4)); await flushPromises();
    expect(getOrders).toHaveBeenCalledTimes(2);
    expect(getOrders).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, assignedToMe: false }));
    expect(JSON.stringify(wrapper.findComponent({ name: 'OrderKanbanBoard' }).props('groupedItems'))).toContain('Заказ 9'); expect(JSON.stringify(wrapper.findComponent({ name: 'OrderKanbanBoard' }).props('groupedItems'))).not.toContain('Заказ 4');
  });
  it('never applies an old response after identity or site changes', async () => {
    const late = deferred<ReturnType<typeof response>>(); vi.spyOn(api, 'getManagerOrders').mockReturnValue(late.promise);
    wrapper = mountDashboard(); await flushPromises(); managerStorefrontSelection.selectedSlug.value = 'other'; await nextTick(); late.resolve(response([order(77)])); await flushPromises(); expect(JSON.stringify(wrapper.findComponent({ name: 'OrderKanbanBoard' }).props('groupedItems'))).not.toContain('Заказ 77');
  });
});


it('restores every board filter from the return URL and keeps its history position', () => {
  window.history.replaceState({ orderListPosition: { top: 300 } }, '', '/manager/orders/kanban?segment=b2b&view=list&groupBy=none&assigned_to_me=1&workFilter=unpaid&hideOnHold=false&status=execution&sort=margin_desc&filtersOpen=true');
  managerSession.auth.value = { staff_user_id: 7 } as any;
  const model = useOrdersDashboardModel(vi.fn());
  model.restorePreferences();
  expect([model.segment.value, model.view.value, model.groupByCustomer.value, model.assignedToMe.value]).toEqual(['b2b', 'list', false, true]);
  expect([model.workFilter.value, model.hideOnHold.value, model.statusFilter.value, model.sort.value, model.filtersOpen.value]).toEqual(['unpaid', false, 'execution', 'margin_desc', true]);
  model.persistGrouping();
  expect(window.history.state.orderListPosition.top).toBe(300);
  managerSession.auth.value = null;
});
