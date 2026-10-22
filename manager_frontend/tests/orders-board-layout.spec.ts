import { nextTick } from 'vue';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrdersDashboard from '../src/components/orders/OrdersDashboard.vue';
import OrderQueueBoard from '../src/components/orders/OrderQueueBoard.vue';
import OrderCardB2B from '../src/components/orders/OrderCardB2B.vue';
import { orderBoardApi } from '../src/services/order-board';
import { managerSession } from '../src/services/manager-session';
import { api } from '../src/api';
import type { ManagerOrderBoardPage, ManagerOrderListItemResponse } from '../src/client';

const order = (id: number, status = 'negotiation') => ({ id, status, title: `Заказ ${id}`, balance_due: 0, customer: { id, type: 'company', name: `Клиент ${id}` } }) as ManagerOrderListItemResponse;
const page = (items: ManagerOrderListItemResponse[], count: number): ManagerOrderBoardPage => ({ items, groups: [], total: count, total_orders: count, page: 1, limit: 25, has_more: true,
  queue_counts: { active: 100, waiting: 5, history: 10000, all: 10105 }, work_counts: { all: 100, followup: 3, planning: 20, unpaid: 2 } });
let wrapper: VueWrapper;
const start = async () => { wrapper = mount(OrdersDashboard, { attachTo: document.body }); await flushPromises(); return wrapper; };
const board = () => wrapper.getComponent(OrderQueueBoard);
const toggle = () => wrapper.get('button[aria-label="Поиск и фильтры"]');
const panel = () => wrapper.get('#orders-options');
const selected = () => board().get('[role="tab"][aria-selected="true"]').attributes('id');
const point = async (target: Element, type: string, x: number, y: number, time: number, pointerType = 'touch') => {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperties(event, Object.fromEntries(Object.entries({ clientX: x, clientY: y, timeStamp: time, pointerId: 1, isPrimary: true, pointerType, _vts: Date.now() + 1 }).map(([key, value]) => [key, { value }])));
  target.dispatchEvent(event); await nextTick();
};
const swipe = async (target: Element, dx = -120, dy = 4, duration = 180, pointerType = 'touch') => {
  await point(target, 'pointerdown', 340, 200, 0, pointerType);
  await point(target, 'pointermove', 340 + dx, 200 + dy, 80, pointerType);
  await point(target, 'pointerup', 340 + dx, 200 + dy, duration, pointerType); await flushPromises();
};
beforeEach(() => {
  vi.useFakeTimers(); localStorage.clear();
  window.history.replaceState({}, '', '/manager/orders?segment=b2b&view=kanban&groupBy=none');
  managerSession.auth.value = { username: 'staff', staff_user_id: 1, tenant_id: 1 } as any;
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.stubGlobal('innerWidth', 390);
  vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => page([order(q.column === 'execution' ? 2 : 1, q.column || 'negotiation')], q.column === 'execution' ? 20 : 80));
});
afterEach(() => { wrapper?.unmount(); managerSession.auth.value = null; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('compact order filters', () => {
  it('starts compact, opens and focuses search in one click, applies immediately and retains its summary when closed', async () => {
    await start(); expect(panel().isVisible()).toBe(false);
    await toggle().trigger('click'); await flushPromises();
    expect(panel().isVisible()).toBe(true); expect(document.activeElement).toBe(wrapper.get('input[aria-label="Поиск заказов"]').element);
    await wrapper.get('input[aria-label="Поиск заказов"]').setValue('Офис'); await vi.advanceTimersByTimeAsync(250); await flushPromises();
    expect(orderBoardApi.page).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'Офис', queue: 'all', limit: 25 }));
    expect(new URLSearchParams(location.search).get('search')).toBe('Офис');
    const requests = vi.mocked(orderBoardApi.page).mock.calls.length;
    await wrapper.get('[aria-label="Закрыть фильтры"]').trigger('click'); await flushPromises();
    expect(panel().isVisible()).toBe(false); expect(wrapper.get('.orders-toolbar').text()).toContain('Офис');
    expect(wrapper.get('.orders-toolbar').get('[aria-label^="Условия:"]').isVisible()).toBe(true);
    expect(orderBoardApi.page).toHaveBeenCalledTimes(requests);
  });
  it('keeps an active search compact on direct navigation and closes explicit open settings with Escape', async () => {
    window.history.replaceState({}, '', '/manager/orders?segment=b2b&search=Объект');
    await start(); expect(panel().isVisible()).toBe(false); expect(wrapper.get('.orders-toolbar').text()).toContain('Объект');
    await toggle().trigger('click'); await flushPromises();
    await wrapper.get('input[aria-label="Поиск заказов"]').trigger('keydown', { key: 'Escape' }); await flushPromises();
    expect(panel().isVisible()).toBe(false); expect(document.activeElement).toBe(toggle().element);
    expect(new URLSearchParams(location.search).get('search')).toBe('Объект');
  });
  it('shows chosen phase/work filters in the compact summary and closes naturally when returning to a card', async () => {
    await start(); await toggle().trigger('click'); await flushPromises();
    await wrapper.get('select[aria-label="Подэтап: Переговоры"]').setValue('follow_up'); await flushPromises();
    const filter = panel().findAll('button').find(b => b.text().startsWith('Есть остаток оплаты'))!;
    await filter.trigger('click'); await flushPromises();
    await wrapper.getComponent(OrderCardB2B).get('article').trigger('click'); await flushPromises();
    expect(panel().isVisible()).toBe(false); expect(wrapper.get('[aria-label^="Условия:"]').text()).toContain('Есть остаток оплаты');
    expect(wrapper.get('[aria-label^="Условия:"]').text()).toContain('Переговоры:');
    expect(new URLSearchParams(location.search).get('workFilter')).toBe('unpaid');
    expect(board().findComponent(OrderCardB2B).props('expanded')).toBe(true);
  });
  it('keeps history/date filters in the disclosure and presents the chosen conditions without an Apply step', async () => {
    await start(); await wrapper.get('nav[aria-label="Очереди заказов"]').findAll('button')[2]!.trigger('click'); await flushPromises();
    expect(panel().isVisible()).toBe(false);
    await toggle().trigger('click'); await wrapper.get('select[aria-label="Результат истории"]').setValue('unknown');
    await wrapper.get('input[aria-label="Дата закрытия с"]').setValue('2026-10-01'); await flushPromises();
    expect(orderBoardApi.page).toHaveBeenLastCalledWith(expect.objectContaining({ queue: 'history', result: 'unknown', closed_from: '2026-10-01', limit: 25 }));
    await wrapper.get('[aria-label="Закрыть фильтры"]').trigger('click'); await flushPromises();
    expect(wrapper.get('[aria-label^="Условия:"]').text()).toContain('Результат: не указан');
    expect(wrapper.get('[aria-label^="Условия:"]').text()).toContain('2026-10-01');
    expect(new URLSearchParams(location.search).get('result')).toBe('unknown');
  });
});

describe('one-tap columns and safe gestures', () => {
  it('shows counted tabs and switches by click or keyboard without fetching another page', async () => {
    await start(); expect(board().find('select[aria-label="Колонка доски"]').exists()).toBe(false);
    expect(board().get('#order-column-tab-negotiation').text()).toBe('Переговоры 80');
    expect(board().get('#order-column-tab-execution').text()).toBe('Работы 20');
    await board().get('#order-column-tab-execution').trigger('click'); expect(selected()).toBe('order-column-tab-execution');
    await board().get('#order-column-tab-execution').trigger('keydown', { key: 'ArrowLeft' }); await flushPromises();
    expect(selected()).toBe('order-column-tab-negotiation'); expect(orderBoardApi.page).toHaveBeenCalledTimes(2);
  });
  it('swipes on free header space and suppresses the accidental compatibility click, while the next tap works', async () => {
    await start(); await swipe(board().get('.column-swipe-hint').element);
    expect(selected()).toBe('order-column-tab-execution');
    { const event = new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }); Object.defineProperty(event, '_vts', { value: Date.now() + 1 }); board().get('#order-column-tab-negotiation').element.dispatchEvent(event); } await nextTick(); expect(selected()).toBe('order-column-tab-execution');
    await point(board().get('#order-column-tab-negotiation').element, 'pointerdown', 30, 200, 300);
    { const event = new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }); Object.defineProperty(event, '_vts', { value: Date.now() + 1 }); board().get('#order-column-tab-negotiation').element.dispatchEvent(event); } await nextTick(); expect(selected()).toBe('order-column-tab-negotiation');
    expect(orderBoardApi.page).toHaveBeenCalledTimes(2);
  });
  it.each(['vertical', 'diagonal', 'short', 'long', 'mouse', 'cancel'])('does not switch for a %s gesture', async kind => {
    await start(); const target = board().get('.column-swipe-hint').element;
    if (kind === 'cancel') { await point(target, 'pointerdown', 340, 200, 0); await point(target, 'pointercancel', 220, 200, 100); await point(target, 'pointerup', 220, 200, 200); }
    else await swipe(target, kind === 'short' ? -30 : kind === 'vertical' ? -4 : -120, kind === 'vertical' ? 120 : kind === 'diagonal' ? 100 : 4, kind === 'long' ? 900 : 180, kind === 'mouse' ? 'mouse' : 'touch');
    expect(selected()).toBe('order-column-tab-negotiation'); expect(orderBoardApi.page).toHaveBeenCalledTimes(2);
  });
  it.each(['card', 'link', 'button', 'tab', 'column background'])('ignores swipe origins on a %s and preserves ordinary card/button clicks', async kind => {
    await start(); const card = board().findComponent(OrderCardB2B);
    const target = kind === 'column background' ? board().get('.queue-scroll').element : kind === 'card' ? card.get('article').element : kind === 'link' ? card.get('a').element : kind === 'button' ? card.get('button[aria-label="Действия с заказом"]').element : board().get('#order-column-tab-negotiation').element;
    await swipe(target); expect(selected()).toBe('order-column-tab-negotiation');
    if (kind === 'card') { await card.get('article').trigger('click'); expect(card.props('expanded')).toBe(true); }
    if (kind === 'button') { await card.get('button[aria-label="Действия с заказом"]').trigger('click'); expect(card.text()).toContain('Пометить отказом'); }
  });
  it('leaves desktop pointer/drag handling and list view outside swipe navigation', async () => {
    await start(); vi.stubGlobal('innerWidth', 1280); await swipe(board().get('.column-swipe-hint').element);
    expect(selected()).toBe('order-column-tab-negotiation');
    const patch = vi.spyOn(api, 'patchManagerOrder').mockResolvedValue(order(1, 'execution') as any);
    await board().findComponent(OrderCardB2B).get('article').trigger('dragstart'); await board().findAll('section')[1]!.trigger('drop'); await flushPromises();
    expect(patch).toHaveBeenCalledExactlyOnceWith(1, expect.objectContaining({ status: 'execution' }));
    wrapper.unmount(); window.history.replaceState({}, '', '/manager/orders?segment=b2b&view=list'); vi.stubGlobal('innerWidth', 390);
    await start(); expect(board().find('[role="tablist"]').exists()).toBe(false);
  });
  it('remembers page positions per mobile column and includes them in return state', async () => {
    let top = 800; vi.spyOn(window, 'scrollY', 'get').mockImplementation(() => top);
    vi.mocked(window.scrollTo).mockImplementation((x: any, y?: number) => { top = typeof x === 'object' ? x.top : y!; });
    await start(); vi.spyOn(board().element, 'getBoundingClientRect').mockImplementation(() => ({ top: 200 - top }) as DOMRect);
    await board().get('#order-column-tab-execution').trigger('click'); await flushPromises(); expect(top).toBe(128);
    top = 600; await board().get('#order-column-tab-negotiation').trigger('click'); await flushPromises(); expect(top).toBe(800);
    const state = (board().vm as any).$.exposed.captureState();
    expect(state.mobileScrollTops).toEqual({ negotiation: 800, execution: 600 });
    expect(state.mobileColumn).toBe('negotiation');
  });
});
