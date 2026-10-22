import { nextTick } from 'vue';
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
import { api } from '../src/api';
import { orderWaitingApi } from '../src/services/order-waiting';
import { orderBoardApi } from '../src/services/order-board';
import OrderQueueBoard from '../src/components/orders/OrderQueueBoard.vue';
import type { ManagerOrderBoardPage } from '../src/client';
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
const response = (items: ManagerOrderListItemResponse[] = [], overrides: Partial<ManagerOrderBoardPage> = {}): ManagerOrderBoardPage => ({
  items, groups: [], page: 1, limit: 25, total: items.length, total_orders: items.length, has_more: false,
  queue_counts: { active: 100, waiting: 5, history: 10000, all: 10105 },
  work_counts: { all: 100, followup: 3, planning: 0, unpaid: 2 }, ...overrides,
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
let wrapper: VueWrapper | undefined;
beforeEach(() => {
  localStorage.clear();
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
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
  global: { stubs: { OrderEditDrawer: true, OrdersImportPreviewModal: true,  } },
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


describe('server queues with the real board', () => {
  it('starts with two bounded active column pages, never fetching history or all pages', async () => {
    const oldList = vi.spyOn(api, 'getManagerOrders');
    const get = vi.spyOn(orderBoardApi, 'page').mockImplementation(async query => response(
      [order(query.column === 'execution' ? 2 : 1)], { total: 100, total_orders: 100, has_more: true },
    ));
    wrapper = mountDashboard(); await flushPromises();
    expect(get).toHaveBeenCalledTimes(2);
    expect(get.mock.calls.map(([q]) => q.column)).toEqual(['negotiation', 'execution']);
    for (const [q] of get.mock.calls) expect(q).toMatchObject({ queue: 'active', page: 1, limit: 25 });
    expect(oldList).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('10000'); // exact history count, zero history cards
    expect(wrapper.findComponent(OrderQueueBoard).exists()).toBe(true);
  });
  it('loads waiting then compact history with explicit unknown result and date filters', async () => {
    const get = vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => response(q.queue === 'history'
      ? [order(3, { status: 'closed', closing_result: null, closed_at: null })]
      : q.column === 'negotiation' ? [order(2, { is_on_hold: true, on_hold_reason: 'Второй этап', next_followup_date: null })] : []));
    wrapper = mountDashboard(); await flushPromises();
    const nav = () => wrapper!.get('nav[aria-label="Очереди заказов"]');
    await nav().findAll('button')[1]!.trigger('click'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ queue: 'waiting' }));
    expect(wrapper.text()).toContain('Второй этап'); expect(wrapper.text()).toContain('Без срока контакта');
    await nav().findAll('button')[2]!.trigger('click'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ queue: 'history', group_by_customer: false }));
    expect(wrapper.text()).toContain('Результат не указан'); expect(wrapper.text()).toContain('Дата закрытия не указана');
    await wrapper.get('select[aria-label="Результат истории"]').setValue('unknown'); await flushPromises();
    await wrapper.get('input[aria-label="Дата закрытия с"]').setValue('2026-09-01'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ result: 'unknown', closed_from: '2026-09-01', include_unknown_date: false }));
    const unknown = wrapper.findAll('label').find(label => label.text().includes('Включить без даты'))!;
    await unknown.get('input').setValue(true); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ include_unknown_date: true }));
  });
  it('searches every queue and shows due waiting contacts without resuming them', async () => {
    const get = vi.spyOn(orderBoardApi, 'page').mockResolvedValue(response([
      order(3, { is_on_hold: true, next_followup_date: '2026-09-01' }),
    ]));
    wrapper = mountDashboard(); await flushPromises(); get.mockClear();
    await wrapper.get('input[aria-label="Поиск заказов"]').setValue('объект');
    await vi.advanceTimersByTimeAsync(250); await flushPromises();
    expect(get).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ queue: 'all', search: 'объект' }));
    expect(wrapper.text()).toContain('Поиск во всех очередях');
    await wrapper.get('input[aria-label="Поиск заказов"]').setValue('');
    await vi.advanceTimersByTimeAsync(250); await flushPromises();
    await wrapper.findAll('button').find(button => button.text().startsWith('Пора связаться'))!.trigger('click'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ work_filter: 'followup', column: undefined }));
    expect(wrapper.text()).toContain('Контакты из активных и ожидающих');
    expect(wrapper.text()).toContain('Ожидание');
  });
  it('lazily pages a large group, keeps its complete totals and retries a child failure', async () => {
    const group = { key: 'customer:1', customer_id: 1, customer_name: 'Большая группа', count: 1000, total_amount: 50000, balance_due: 12500, margin: 10000 };
    const get = vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => {
      if (q.group_key) return response([order(q.page === 1 ? 1 : 2)], { page: q.page!, total: 1000, total_orders: 1000, has_more: true });
      return response([], { groups: q.column === 'negotiation' ? [group] : [], total: 1, total_orders: 1000 });
    });
    wrapper = mountDashboard(); await flushPromises();
    expect(get).toHaveBeenCalledTimes(2);
    await wrapper.findAll('button').find(button => button.text().includes('Показать заказы'))!.trigger('click'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ group_key: 'customer:1', page: 1, limit: 25 }));
    expect(wrapper.text()).toContain('Загружено 1 из 1000'); expect(wrapper.text()).toContain('Итоги выше — по всей группе');
    get.mockRejectedValueOnce(new Error('offline'));
    await wrapper.findAll('button').find(button => button.text() === 'Ещё заказы')!.trigger('click'); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('offline'); expect(wrapper.text()).toContain('Заказ 1');
    await wrapper.findAll('button').find(button => button.text() === 'Повторить')!.trigger('click'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    expect(wrapper.text()).toContain('Загружено 2 из 1000');
  });
  it('keeps the other column and its phase independent when one phase changes', async () => {
    const get = vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => response([order(q.column === 'execution' ? 2 : 1)], { has_more: true, total: 50, total_orders: 50 }));
    wrapper = mountDashboard(); await flushPromises(); get.mockClear();
    await wrapper.get('select[aria-label="Подэтап: Переговоры"]').setValue('follow_up'); await flushPromises();
    expect(get).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ column: 'negotiation', phase: 'follow_up' }));
    expect(wrapper.text()).toContain('Заказ 2');
    const sections = wrapper.findAll('section.queue-column');
    await sections[1]!.findAll('button').find(button => button.text() === 'Показать ещё')!.trigger('click'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ column: 'execution', phase: undefined, page: 2 }));
  });
  it('rejects stale search/context responses and retains assignment/customer filters on paging', async () => {
    managerSession.auth.value = { staff_user_id: 7, tenant_id: 1, username: 'maria' } as any;
    window.history.replaceState({}, '', '/manager/orders?segment=all&assigned_to_me=1&customerId=42&groupBy=none');
    const late = deferred<ManagerOrderBoardPage>();
    const get = vi.spyOn(orderBoardApi, 'page').mockReturnValueOnce(late.promise).mockResolvedValue(response([order(9)], { has_more: true }));
    wrapper = mountDashboard(); await flushPromises();
    await wrapper.get('input[aria-label="Поиск заказов"]').setValue('new');
    late.resolve(response([order(77)])); await flushPromises();
    expect(wrapper.text()).not.toContain('Заказ 77');
    await vi.advanceTimersByTimeAsync(250); await flushPromises();
    await wrapper.findAll('button').find(button => button.text() === 'Показать ещё')!.trigger('click'); await flushPromises();
    expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ customer_id: 42, assigned_to_me: true, page: 2, search: 'new' }));
    const old = deferred<ManagerOrderBoardPage>(); get.mockReturnValueOnce(old.promise);
    await wrapper.findAll('button').find(button => button.text() === 'Показать ещё')!.trigger('click');
    managerStorefrontSelection.selectedSlug.value = 'other'; await nextTick(); old.resolve(response([order(88)])); await flushPromises();
    expect(wrapper.text()).not.toContain('Заказ 88');
    managerSession.auth.value = null; managerStorefrontSelection.selectedSlug.value = null;
  });
  it('shows a retryable initial failure and retains the selected mobile column state', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(orderBoardApi, 'page').mockRejectedValueOnce(new Error('offline')).mockResolvedValue(response([order(1)]));
    wrapper = mountDashboard(); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('offline');
    expect(wrapper.text()).toContain('Заказ 1');
    await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises();
    const board = wrapper.getComponent(OrderQueueBoard);
    await board.get('#order-column-tab-execution').trigger('click'); await flushPromises();
    const state = (board.vm as any).$.exposed.captureState();
    expect(state.mobileColumn).toBe('execution');
    await board.get('#order-column-tab-negotiation').trigger('click'); await flushPromises();
    await (board.vm as any).$.exposed.restoreState(state); await nextTick();
    expect(board.get('#order-column-tab-execution').attributes('aria-selected')).toBe('true');
  });
});


it('retains list selection/export controls, server sorting and scoped group aliases', async () => {
  window.history.replaceState({}, '', '/manager/orders?segment=all&view=list&groupBy=none');
  const get = vi.spyOn(orderBoardApi, 'page').mockResolvedValue(response([order(1), order(2)]));
  wrapper = mountDashboard(); await flushPromises();
  const checkbox = wrapper.get('input[aria-label="Выбрать заказ #1"]');
  await checkbox.setValue(true);
  expect(wrapper.text()).toContain('Экспорт 1');
  const sortButton = wrapper.findAll('button').find(button => button.text().includes('Заказ и клиент'))!;
  await sortButton.trigger('click'); await flushPromises();
  expect(get).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'created_at_asc', page: 1 }));
});

it('restores loaded group children and scroll positions from the return history entry', async () => {
  const url = '/manager/orders?segment=all&view=kanban&groupBy=customer';
  const group = { key: 'customer:1', customer_id: 1, customer_name: 'Group', count: 100, total_amount: 1000, balance_due: 500 };
  window.history.replaceState({ orderListPosition: { url, top: 345, board: {
    expandedOrderId: 1, expandedGroupIds: ['negotiation/customer:1'], columnFilters: { negotiation: 'follow_up' }, scrollLeft: 0,
    mobileScrollTops: { negotiation: 234, execution: 345 }, loadedPages: { negotiation: 1, execution: 1, 'negotiation/customer:1': 2 }, mobileColumn: 'execution',
  } } }, '', url);
  const get = vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => q.group_key
    ? response([order(q.page!)], { page: q.page!, total: 100, total_orders: 100, has_more: true })
    : response([], { groups: q.column === 'negotiation' ? [group] : [] }));
  wrapper = mountDashboard(); await flushPromises();
  expect(get.mock.calls.filter(([q]) => q.group_key).map(([q]) => q.page)).toEqual([1, 2]);
  expect(wrapper.text()).toContain('Загружено 2 из 100');
  const board = wrapper.getComponent(OrderQueueBoard);
  expect(window.scrollTo).toHaveBeenLastCalledWith(0, 345);
  expect((board.vm as any).$.exposed.captureState().mobileScrollTops.negotiation).toBe(234);
  expect(wrapper.get('#order-column-tab-execution').attributes('aria-selected')).toBe('true');
  expect(wrapper.get('select[aria-label="Подэтап: Переговоры"]').element).toHaveProperty('value', 'follow_up');
});


it('keeps a single phase source across queue changes and clears it with Reset', async () => {
  const get = vi.spyOn(orderBoardApi, 'page').mockResolvedValue(response([order(1)]));
  wrapper = mountDashboard(); await flushPromises();
  await wrapper.get('select[aria-label="Подэтап: Переговоры"]').setValue('follow_up'); await flushPromises();
  await wrapper.get('nav').findAll('button')[1]!.trigger('click'); await flushPromises();
  expect(wrapper.get('select[aria-label="Подэтап: Переговоры"]').element).toHaveProperty('value', 'follow_up');
  expect(get.mock.calls.slice(-2).find(([q]) => q.column === 'negotiation')?.[0].phase).toBe('follow_up');
  await wrapper.findAll('button').find(button => button.text().includes('Сбросить фильтры'))!.trigger('click'); await flushPromises();
  expect(wrapper.get('select[aria-label="Подэтап: Переговоры"]').element).toHaveProperty('value', '');
  expect(get.mock.calls.slice(-2).every(([q]) => !q.phase)).toBe(true);
});

it('uses the displayed phase when dropping a card into a column', async () => {
  vi.spyOn(orderBoardApi, 'page').mockResolvedValue(response([order(1)]));
  wrapper = mountDashboard(); await flushPromises();
  await wrapper.get('select[aria-label="Подэтап: Работы"]').setValue('scheduled'); await flushPromises();
  const board = wrapper.getComponent(OrderQueueBoard);
  const card = board.findComponent({ name: 'OrderCardB2B' });
  card.vm.$emit('dragStart', { orderId: 1, oldStatus: 'negotiation' });
  await board.findAll('section')[1]!.trigger('drop');
  expect(board.emitted('move')?.[0]).toEqual([{ orderId: 1, oldStatus: 'negotiation', newStatus: 'execution:scheduled' }]);
});

it('renders compact grouped list rows and queue labels in search results', async () => {
  window.history.replaceState({}, '', '/manager/orders?segment=all&view=list&groupBy=customer');
  const group = { key: 'customer:1', customer_id: 1, customer_name: 'Group', count: 2, total_amount: 200, balance_due: 100 };
  vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => q.search || q.group_key
    ? response([order(1), order(2, { is_on_hold: true })]) : response([], { groups: [group] }));
  wrapper = mountDashboard(); await flushPromises();
  await wrapper.findAll('button').find(button => button.text().includes('Показать заказы'))!.trigger('click'); await flushPromises();
  expect(wrapper.find('table').exists()).toBe(true);
  expect(wrapper.findComponent({ name: 'OrderCardB2B' }).exists()).toBe(false);
  await wrapper.get('input[aria-label="Поиск заказов"]').setValue('office');
  await vi.advanceTimersByTimeAsync(250); await flushPromises();
  expect(wrapper.get('tbody').text()).toContain('Активные');
  expect(wrapper.get('tbody').text()).toContain('Ожидание');
});

it('renders singleton groups immediately without lazy child requests', async () => {
  const get = vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => response(q.column === 'negotiation' ? [order(1)] : [], {
    groups: q.column === 'negotiation' ? [{ key: 'customer:1', customer_id: 1, order_id: 1, customer_name: 'One', count: 1, total_amount: 100, balance_due: 100 }] : [],
  }));
  wrapper = mountDashboard(); await flushPromises();
  expect(get).toHaveBeenCalledTimes(2);
  expect(wrapper.text()).toContain('Заказ 1');
  expect(wrapper.text()).not.toContain('Показать заказы');
});

it('blocks all cards when a column returns an authorization failure', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {});
  vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => {
    if (q.column === 'negotiation') throw { status: 403, message: 'Access revoked' };
    return response([order(99)]);
  });
  wrapper = mountDashboard(); await flushPromises();
  expect(wrapper.text()).not.toContain('Заказ 99');
  expect(wrapper.find('[role="alert"]').exists()).toBe(true);
});


describe('explicit waiting on real cards', () => {
  const open = async (held = false) => {
    vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => response(q.column === 'execution' ? [] : [order(1, { workflow_revision: 6, is_on_hold: held })]));
    wrapper = mountDashboard(); await flushPromises();
    const action = wrapper.findAll('button').find(button => button.text() === (held ? 'Вернуть в работу' : 'В ожидание'))!;
    await action.trigger('click'); await flushPromises();
  };
  const dialog = () => new DOMWrapper(document.querySelector('[aria-labelledby="order-waiting-title"]')!);
  it('waits indefinitely with a reason and resumes directly without another dialog', async () => {
    const command = vi.spyOn(orderWaitingApi, 'command').mockResolvedValue(order(1, { is_on_hold: true, workflow_revision: 7 }) as any);
    await open();
    expect(command).not.toHaveBeenCalled();
    expect(dialog().get('input[aria-label="Контрольный контакт"]').element).toHaveProperty('value', '');
    await dialog().get('select[aria-label="Причина ожидания"]').setValue('next_stage');
    await dialog().get('form').trigger('submit'); await flushPromises();
    expect(command).toHaveBeenCalledExactlyOnceWith(1, { action: 'wait', expected_revision: 6, reason_code: 'next_stage', note: null, next_followup_date: null });
    expect(document.querySelector('[aria-labelledby="order-waiting-title"]')).toBeNull();
    wrapper!.unmount(); wrapper = undefined; command.mockClear();
    await open(true);
    expect(command).toHaveBeenCalledExactlyOnceWith(1, { action: 'resume', expected_revision: 6 });
    expect(document.querySelector('[aria-labelledby="order-waiting-title"]')).toBeNull();
  });
  it('retains explanation and contact on 409 and refreshes the revision only on request', async () => {
    const command = vi.spyOn(orderWaitingApi, 'command').mockRejectedValueOnce({ status: 409, body: { detail: { message: 'Этап изменился' } } })
      .mockResolvedValue(order(1, { is_on_hold: true, workflow_revision: 9 }) as any);
    const get = vi.spyOn(api, 'getManagerOrderDetail').mockResolvedValue(order(1, { workflow_revision: 8 }) as any);
    await open();
    await dialog().get('select').setValue('other');
    await dialog().get('textarea').setValue('Сохранить мой текст');
    await dialog().get('input').setValue('2027-03-01T10:30');
    await dialog().get('form').trigger('submit'); await flushPromises();
    expect(dialog().get('[role="alert"]').text()).toContain('Этап изменился');
    expect(dialog().get('textarea').element).toHaveProperty('value', 'Сохранить мой текст');
    expect(dialog().get('input').element).toHaveProperty('value', '2027-03-01T10:30');
    expect(command).toHaveBeenCalledTimes(1); expect(get).not.toHaveBeenCalled();
    await dialog().findAll('button').find(button => button.text() === 'Обновить сведения')!.trigger('click'); await flushPromises();
    expect(command).toHaveBeenCalledTimes(1);
    expect(dialog().get('textarea').element).toHaveProperty('value', 'Сохранить мой текст');
    await dialog().get('form').trigger('submit'); await flushPromises();
    expect(command).toHaveBeenLastCalledWith(1, expect.objectContaining({ expected_revision: 8, note: 'Сохранить мой текст', next_followup_date: '2027-03-01T10:30:00' }));
  });
  it('keeps input and a retryable error on network failure without moving the order', async () => {
    const command = vi.spyOn(orderWaitingApi, 'command').mockRejectedValueOnce(new Error('offline'));
    await open(); await dialog().get('textarea').setValue('Ожидание объекта');
    await dialog().get('form').trigger('submit'); await flushPromises();
    expect(dialog().get('[role="alert"]').text()).toContain('offline');
    expect(dialog().get('textarea').element).toHaveProperty('value', 'Ожидание объекта');
    expect(command).toHaveBeenCalledTimes(1);
    expect(wrapper!.text()).toContain('Заказ 1');
  });
});
