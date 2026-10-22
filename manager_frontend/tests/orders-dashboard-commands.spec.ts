import { nextTick } from 'vue';
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/api';
import { orderBoardApi, type BoardQuery } from '../src/services/order-board';
import { orderWaitingApi } from '../src/services/order-waiting';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
import { resetUiFeedbackForTests, uiDialogState } from '../src/services/ui-feedback';
import type { ManagerOrderBoardPage, ManagerOrderListItemResponse } from '../src/client';
import OrdersDashboard from '../src/components/orders/OrdersDashboard.vue';
import OrderQueueBoard from '../src/components/orders/OrderQueueBoard.vue';
import OrderCardB2B from '../src/components/orders/OrderCardB2B.vue';
import OrderWaitingDialog from '../src/components/orders/OrderWaitingDialog.vue';
import OrderTitleEditor from '../src/components/orders/OrderTitleEditor.vue';
import UiFeedbackHost from '../src/components/common/UiFeedbackHost.vue';

const order = (id: number, extra: Partial<ManagerOrderListItemResponse> = {}) => ({
  id, title: `Заказ ${id}`, status: 'negotiation', negotiation_status: 'follow_up', workflow_revision: 3,
  balance_due: 0, total_amount: 100, total_cost: 50, margin: 50, is_on_hold: false,
  customer: { id, name: `Клиент ${id}`, type: 'company' }, ...extra,
}) as ManagerOrderListItemResponse;
const page = (items: ManagerOrderListItemResponse[], extra: Partial<ManagerOrderBoardPage> = {}): ManagerOrderBoardPage => ({
  items, groups: [], page: 1, limit: 25, total: items.length, total_orders: items.length, has_more: false,
  queue_counts: { active: items.length, waiting: 0, history: 0, all: items.length },
  work_counts: { all: items.length, followup: 0, planning: 0, unpaid: 0 }, ...extra,
});
const deferred = <T,>() => {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
let wrapper: VueWrapper, host: VueWrapper, rows: ManagerOrderListItemResponse[];
const read = (q: BoardQuery) => {
  const live = rows.filter(o => o.status !== 'closed' && !o.is_on_hold);
  const selected = rows.filter(o => q.queue === 'all' || q.queue === 'history' ? q.queue === 'all' || o.status === 'closed' : o.status !== 'closed' && !!o.is_on_hold === (q.queue === 'waiting'))
    .filter(o => !q.column || o.status === q.column).filter(o => !q.search || o.title?.includes(q.search));
  return page(structuredClone(selected), { queue_counts: { active: live.length, waiting: rows.filter(o => o.is_on_hold && o.status !== 'closed').length,
    history: rows.filter(o => o.status === 'closed').length, all: rows.length } });
};
const start = async () => { host = mount(UiFeedbackHost); wrapper = mount(OrdersDashboard); await flushPromises(); };
const card = (id: number) => wrapper.findAllComponents(OrderCardB2B).find(c => c.props('order').id === id)!;
const button = (root: VueWrapper | DOMWrapper<Element>, text: string) => root.findAll('button').find(b => b.text().replace('◌', '').replace(' · Сохранение…', '').trim() === text)!;
const dialog = () => new DOMWrapper(document.querySelector('[aria-labelledby="ui-dialog-title"]')!);
const waitingDialog = () => new DOMWrapper(document.querySelector('[aria-labelledby="order-waiting-title"]')!);
const action = async (id: number, text: string) => { await card(id).get('[aria-label="Действия с заказом"]').trigger('click'); await card(id).findAll('button').find(b => b.text().endsWith(text))!.trigger('click'); await flushPromises(); };
const rename = async (id: number, title: string) => { const editor = card(id).getComponent(OrderTitleEditor); await editor.get('p').trigger('dblclick'); await editor.get('input').setValue(title); await editor.get('input').trigger('keydown.enter'); await flushPromises(); };

beforeEach(() => {
  localStorage.clear(); resetUiFeedbackForTests(); vi.useFakeTimers();
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  window.history.replaceState({}, '', '/manager/orders?segment=b2b&view=kanban&groupBy=none');
  managerSession.auth.value = { username: 'staff', tenant_id: 1, staff_user_id: 1 } as any;
  rows = [order(1), order(2)];
  vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => read(q));
});
afterEach(() => { wrapper?.unmount(); host?.unmount(); resetUiFeedbackForTests(); vi.restoreAllMocks(); vi.useRealTimers(); managerSession.auth.value = null; managerStorefrontSelection.selectedSlug.value = null; });

describe('board commands with real menus and dialogs', () => {
  it('cancels refusal without changing anything and keeps the reason editable after a failed save', async () => {
    const patch = vi.spyOn(api, 'patchManagerOrder').mockRejectedValueOnce(new Error('offline')).mockImplementation(async (id, payload) => {
      Object.assign(rows.find(o => o.id === id)!, payload); return rows.find(o => o.id === id)! as any;
    });
    await start(); await action(1, 'Пометить отказом');
    await dialog().get('textarea').setValue('Первый вариант'); await button(dialog(), 'Отмена').trigger('click'); await flushPromises();
    expect(patch).not.toHaveBeenCalled(); expect(card(1).exists()).toBe(true);
    await action(1, 'Пометить отказом'); await dialog().get('textarea').setValue('Клиент отказался от этапа');
    await button(dialog(), 'Пометить отказом').trigger('click'); await flushPromises();
    expect(dialog().get('[role="alert"]').text()).toContain('offline');
    expect(dialog().get('textarea').element).toHaveProperty('value', 'Клиент отказался от этапа');
    expect(dialog().get('textarea').attributes('disabled')).toBeUndefined();
    expect(wrapper.text()).not.toContain('Заказ помечен отказом'); expect(card(1).props('order').status).toBe('negotiation');
    await button(dialog(), 'Пометить отказом').trigger('click'); await flushPromises();
    expect(patch).toHaveBeenLastCalledWith(1, { status: 'closed', closing_result: 'lost', reject_reason: 'Клиент отказался от этапа' });
    expect(uiDialogState.open).toBe(false); expect(card(1)).toBeUndefined(); expect(card(2).exists()).toBe(true);
    expect(wrapper.get('nav').text()).toContain('Активные 1'); expect(wrapper.get('nav').text()).toContain('История 1');
  });
  it('only exposes compact terminal drop targets while dragging and shares refusal retry/cancel', async () => {
    const patch = vi.spyOn(api, 'patchManagerOrder').mockRejectedValue(new Error('drop offline'));
    await start(); expect(wrapper.find('[data-drop-status]').exists()).toBe(false);
    await card(1).get('[draggable]').trigger('dragstart');
    expect(wrapper.findAll('[data-drop-status]')).toHaveLength(2);
    await card(1).get('[draggable]').trigger('dragend'); await nextTick(); expect(wrapper.find('[data-drop-status]').exists()).toBe(false);
    await card(1).get('[draggable]').trigger('dragstart'); await wrapper.get('[data-drop-status="closed_lost"]').trigger('drop'); await flushPromises();
    expect(wrapper.find('[data-drop-status]').exists()).toBe(false); expect(patch).not.toHaveBeenCalled();
    await dialog().get('textarea').setValue('Причина из drop'); await button(dialog(), 'Пометить отказом').trigger('click'); await flushPromises();
    expect(dialog().get('textarea').element).toHaveProperty('value', 'Причина из drop'); expect(dialog().text()).toContain('drop offline');
    await button(dialog(), 'Отмена').trigger('click'); await flushPromises(); expect(card(1).props('order').status).toBe('negotiation');
  });
  it('completes a dropped order and revalidates exact membership and counters', async () => {
    const patch = vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { Object.assign(rows.find(o => o.id === id)!, payload); return rows[0]! as any; });
    await start(); await card(1).get('[draggable]').trigger('dragstart'); await wrapper.get('[data-drop-status="closed_won"]').trigger('drop'); await flushPromises();
    expect(patch).toHaveBeenCalledExactlyOnceWith(1, { status: 'closed', closing_result: 'won', reject_reason: null });
    expect(card(1)).toBeUndefined(); expect(wrapper.get('nav').text()).toContain('Активные 1');
  });
  it('does not roll back B when A fails later; pending controls prevent a repeated A', async () => {
    const a = deferred<any>();
    const patch = vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => {
      if (id === 1) return a.promise;
      Object.assign(rows[1]!, payload); return structuredClone(rows[1]!) as any;
    });
    await start(); await rename(1, 'Не сохранится');
    expect(card(1).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeDefined();
    wrapper.getComponent(OrderQueueBoard).vm.$emit('renameOrder', { orderId: 1, title: 'Повтор' }); await flushPromises();
    expect(patch).toHaveBeenCalledTimes(1);
    await action(2, 'Завершить успешно'); expect(card(2)).toBeUndefined();
    a.reject(new Error('A offline')); await flushPromises();
    expect(card(1).props('order').title).toBe('Заказ 1'); expect(card(2)).toBeUndefined();
    expect(wrapper.get('nav').text()).toContain('История 1'); expect(wrapper.text()).toContain('A offline');
  });
  it('coalesces overlapping revalidations but reruns reads after the later write', async () => {
    const snapshot = deferred<ManagerOrderBoardPage>();
    const get = vi.mocked(orderBoardApi.page); let held = false;
    vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { Object.assign(rows.find(o => o.id === id)!, payload); return structuredClone(rows.find(o => o.id === id)!) as any; });
    await start(); get.mockImplementation(async q => { if (!held && q.column === 'negotiation') { held = true; return snapshot.promise; } return read(q); });
    await rename(1, 'Первый сохранён');
    const oldSnapshot = read({ segment: 'b2b', queue: 'active', column: 'negotiation' });
    await action(2, 'Завершить успешно'); // B is allowed while A refreshes.
    snapshot.resolve(oldSnapshot); await flushPromises();
    expect(card(1).props('order').title).toBe('Первый сохранён'); expect(card(2)).toBeUndefined();
    expect(get.mock.calls.filter(([q]) => q.column === 'negotiation')).toHaveLength(3); // initial, stale, latest
    expect(wrapper.get('nav').text()).toContain('История 1');
  });
  it.each(['search', 'segment', 'phase'])('keeps the sent order locked across a %s change until the mock-server write and current read settle', async context => {
    const old = deferred<void>(); let callsA = 0, activeA = 0, maxActiveA = 0;
    const patch = vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => {
      if (id === 1) {
        activeA++; maxActiveA = Math.max(maxActiveA, activeA);
        if (++callsA === 1) await old.promise;
      }
      // The old request really writes on completion, after the filter has changed.
      Object.assign(rows.find(o => o.id === id)!, payload);
      if (id === 1) activeA--;
      return structuredClone(rows.find(o => o.id === id)!) as any;
    });
    await start(); await rename(1, 'Заказ: отложенная запись');
    if (context === 'search') { await wrapper.get('input[aria-label="Поиск заказов"]').setValue('Заказ'); await vi.advanceTimersByTimeAsync(250); }
    if (context === 'segment') wrapper.getComponent({ name: 'OrdersToolbar' }).vm.$emit('update:segment', 'all');
    if (context === 'phase') await wrapper.get('select[aria-label="Подэтап: Переговоры"]').setValue('follow_up');
    await flushPromises();
    expect(card(1).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeDefined();
    wrapper.getComponent(OrderQueueBoard).vm.$emit('renameOrder', { orderId: 1, title: 'Нельзя отправить параллельно' }); await flushPromises();
    expect(callsA).toBe(1);
    await rename(2, 'Заказ B сохранён'); // Other orders remain independent.
    expect(rows[1]!.title).toBe('Заказ B сохранён');
    await vi.advanceTimersByTimeAsync(2500); await flushPromises();
    const reads = vi.mocked(orderBoardApi.page).mock.calls.length;
    old.resolve(); await flushPromises();
    expect(rows[0]!.title).toBe('Заказ: отложенная запись');
    expect(card(1).props('order').title).toBe('Заказ: отложенная запись');
    expect(card(2).props('order').title).toBe('Заказ B сохранён');
    expect(vi.mocked(orderBoardApi.page).mock.calls.length).toBeGreaterThan(reads);
    expect(wrapper.text()).not.toContain('Название заказа сохранено'); // Obsolete success has no UI ownership.
    expect(card(1).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeUndefined();
    await rename(1, 'Заказ: новая запись');
    expect(rows[0]!.title).toBe('Заказ: новая запись'); expect(card(1).props('order').title).toBe(rows[0]!.title);
    expect(maxActiveA).toBe(1); expect(patch).toHaveBeenCalledTimes(3);
  });
  it('does not regain success ownership when filters return to the original values during a write', async () => {
    const old = deferred<void>();
    const patch = vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { await old.promise; Object.assign(rows.find(o => o.id === id)!, payload); return rows[0]! as any; });
    await start(); await rename(1, 'Отложенная запись');
    const toolbar = wrapper.getComponent({ name: 'OrdersToolbar' });
    toolbar.vm.$emit('update:segment', 'all'); await flushPromises();
    toolbar.vm.$emit('update:segment', 'b2b'); await flushPromises();
    wrapper.getComponent(OrderQueueBoard).vm.$emit('renameOrder', { orderId: 1, title: 'Не отправлять' }); await flushPromises();
    expect(patch).toHaveBeenCalledTimes(1);
    old.resolve(); await flushPromises();
    expect(card(1).props('order').title).toBe('Отложенная запись');
    expect(wrapper.text()).not.toContain('Название заказа сохранено');
    expect(card(1).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeUndefined();
  });
  it('keeps different identities independent and ignores a response from the previous tenant', async () => {
    const old = deferred<any>(); let call = 0;
    const patch = vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => {
      if (++call === 1) return old.promise;
      Object.assign(rows.find(o => o.id === id)!, payload); return structuredClone(rows.find(o => o.id === id)!) as any;
    });
    await start(); await rename(1, 'Старый tenant');
    managerSession.auth.value = { ...managerSession.auth.value, tenant_id: 2 } as any;
    await flushPromises(); wrapper.unmount(); host.unmount(); await start();
    await rename(1, 'Другой tenant'); expect(patch).toHaveBeenCalledTimes(2);
    const reads = vi.mocked(orderBoardApi.page).mock.calls.length;
    old.resolve(order(1, { title: 'Ответ предыдущего tenant' })); await flushPromises();
    expect(card(1).props('order').title).toBe('Другой tenant'); expect(vi.mocked(orderBoardApi.page).mock.calls.length).toBe(reads);
  });
  it('releases a dialog cancelled by a filter change before any write was sent', async () => {
    const patch = vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { Object.assign(rows.find(o => o.id === id)!, payload); return rows[0]! as any; });
    await start(); await action(1, 'Пометить отказом');
    await dialog().get('textarea').setValue('Не отправленная причина');
    wrapper.getComponent({ name: 'OrdersToolbar' }).vm.$emit('update:segment', 'all'); await flushPromises();
    expect(uiDialogState.open).toBe(false); expect(patch).not.toHaveBeenCalled();
    expect(card(1).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeUndefined();
    await action(1, 'Пометить отказом'); await dialog().get('textarea').setValue('Текущая причина');
    await button(dialog(), 'Пометить отказом').trigger('click'); await flushPromises();
    expect(patch).toHaveBeenCalledExactlyOnceWith(1, expect.objectContaining({ reject_reason: 'Текущая причина' }));
  });
  it('refreshes the new search immediately if an old write settles inside its debounce window', async () => {
    const old = deferred<void>();
    vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { await old.promise; Object.assign(rows.find(o => o.id === id)!, payload); return rows[0]! as any; });
    await start(); await rename(1, 'Заказ: найден после записи');
    await wrapper.get('input[aria-label="Поиск заказов"]').setValue('найден');
    old.resolve(); await flushPromises();
    expect(vi.mocked(orderBoardApi.page)).toHaveBeenLastCalledWith(expect.objectContaining({ search: 'найден', queue: 'all' }));
    expect(card(1).props('order').title).toBe('Заказ: найден после записи'); expect(card(2)).toBeUndefined();
    const reads = vi.mocked(orderBoardApi.page).mock.calls.length;
    await vi.advanceTimersByTimeAsync(250); await flushPromises(); expect(vi.mocked(orderBoardApi.page).mock.calls.length).toBe(reads);
    expect(wrapper.text()).not.toContain('Название заказа сохранено');
  });
  it('closes an old refusal on context change, and its late result cannot close a new dialog', async () => {
    const old = deferred<void>(); const patch = vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { await old.promise; Object.assign(rows.find(o => o.id === id)!, payload); return structuredClone(rows.find(o => o.id === id)!) as any; });
    await start(); await action(1, 'Пометить отказом');
    await dialog().get('textarea').setValue('Старый контекст'); await button(dialog(), 'Пометить отказом').trigger('click'); await flushPromises();
    wrapper.getComponent({ name: 'OrdersToolbar' }).vm.$emit('update:segment', 'all'); await flushPromises();
    expect(uiDialogState.open).toBe(false);
    await vi.advanceTimersByTimeAsync(0); await action(2, 'Пометить отказом'); await dialog().get('textarea').setValue('Новая причина');
    wrapper.getComponent(OrderQueueBoard).vm.$emit('renameOrder', { orderId: 1, title: 'Не отправлять второй PATCH' }); await flushPromises();
    expect(patch).toHaveBeenCalledTimes(1);
    old.resolve(); await flushPromises();
    expect(card(1)).toBeUndefined();
    expect(uiDialogState.open).toBe(true); expect(dialog().get('textarea').element).toHaveProperty('value', 'Новая причина');
    expect(wrapper.text()).not.toContain('Заказ помечен отказом');
  });
  it('distinguishes saved command from failed revalidation, keeps the board and retries the read', async () => {
    vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { Object.assign(rows.find(o => o.id === id)!, payload); return rows[0]! as any; });
    await start(); const get = vi.mocked(orderBoardApi.page); get.mockRejectedValue(new Error('read offline'));
    await action(1, 'Пометить отказом'); await dialog().get('textarea').setValue('Сохранено'); await button(dialog(), 'Пометить отказом').trigger('click'); await flushPromises();
    expect(uiDialogState.open).toBe(false); expect(wrapper.text()).toContain('Заказ помечен отказом. Не удалось обновить доску');
    expect(wrapper.text()).not.toContain('Не удалось закрыть отказ'); expect(wrapper.text()).toContain('Показаны предыдущие данные');
    expect(card(2).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeDefined();
    expect(wrapper.get('nav').text()).not.toMatch(/Активные 2/);
    get.mockImplementation(async q => read(q)); await button(wrapper, 'Повторить загрузку').trigger('click'); await flushPromises();
    expect(card(1)).toBeUndefined(); expect(card(2).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeUndefined();
  });
  it('retains expanded lazy children, bounded page counts and exact group totals after another order changes', async () => {
    window.history.replaceState({}, '', '/manager/orders?segment=b2b&groupBy=customer');
    const group = { key: 'customer:9', customer_id: 9, customer_name: 'Большая группа', count: 1000, total_amount: 100000, balance_due: 50000 };
    rows = [order(2, { status: 'execution' })];
    const get = vi.mocked(orderBoardApi.page).mockImplementation(async q => q.group_key
      ? page([order(q.page === 1 ? 11 : 12)], { page: q.page!, total: 1000, total_orders: 1000, has_more: true })
      : q.column === 'negotiation' ? page([], { groups: [group], total_orders: 1000, total: 1 }) : read(q));
    vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (_id, payload) => { Object.assign(rows[0]!, payload); return rows[0]! as any; });
    await start();
    // Match the accessible group toggle independently of money locale formatting.
    if (!wrapper.text().includes('Загружено')) { await wrapper.findAll('button').find(b => b.attributes('aria-expanded') === 'false' && b.text().includes('Большая группа'))!.trigger('click'); }
    await flushPromises(); await button(wrapper, 'Ещё заказы').trigger('click'); await flushPromises();
    const board = wrapper.getComponent(OrderQueueBoard);
    get.mockClear();
    await rename(2, 'Другой заказ изменён');
    expect(wrapper.getComponent(OrderQueueBoard).element).toBe(board.element);
    expect(wrapper.text()).toContain('Загружено 2 из 1000');
    expect(wrapper.text()).toContain('Заказ 11'); expect(wrapper.text()).toContain('Заказ 12');
    expect(get.mock.calls.filter(([q]) => q.group_key).map(([q]) => q.page)).toEqual([1, 2]);
    expect(get.mock.calls.every(([q]) => q.limit === 25)).toBe(true);
    expect(board.find('[aria-expanded="true"]').exists()).toBe(true);
  });
});

describe('waiting shares command ownership', () => {
  it('allows two different resume commands and visibly disables only their own controls', async () => {
    rows = [order(1, { is_on_hold: true }), order(2, { is_on_hold: true })];
    window.history.replaceState({}, '', '/manager/orders?segment=b2b&groupBy=none&queue=waiting');
    const a = deferred<any>(), b = deferred<any>(); const command = vi.spyOn(orderWaitingApi, 'command').mockImplementation(id => id === 1 ? a.promise : b.promise);
    await start(); await button(card(1), 'Вернуть в работу').trigger('click'); await flushPromises();
    expect(button(card(1), 'Вернуть в работу').attributes('disabled')).toBeDefined();
    expect(button(card(2), 'Вернуть в работу').attributes('disabled')).toBeUndefined();
    await button(card(2), 'Вернуть в работу').trigger('click'); await flushPromises(); expect(command).toHaveBeenCalledTimes(2);
    rows[1]!.is_on_hold = false; b.resolve(structuredClone(rows[1]!)); await flushPromises();
    expect(card(2)).toBeUndefined(); rows[0]!.is_on_hold = false; a.resolve(structuredClone(rows[0]!)); await flushPromises();
    expect(card(1)).toBeUndefined(); expect(wrapper.get('nav').text()).toContain('Ожидание 0');
  });
  it('retains a sent waiting lock across filters and revalidates the current queue without a stale toast', async () => {
    const old = deferred<void>();
    const patch = vi.spyOn(api, 'patchManagerOrder');
    vi.spyOn(orderWaitingApi, 'command').mockImplementation(async id => { await old.promise; rows.find(o => o.id === id)!.is_on_hold = true; return structuredClone(rows.find(o => o.id === id)!) as any; });
    await start(); await button(card(1), 'В ожидание').trigger('click'); await flushPromises();
    await waitingDialog().get('form').trigger('submit'); await flushPromises();
    wrapper.getComponent({ name: 'OrdersToolbar' }).vm.$emit('update:segment', 'all'); await flushPromises();
    wrapper.getComponent(OrderQueueBoard).vm.$emit('renameOrder', { orderId: 1, title: 'Запрещён параллельный PATCH' }); await flushPromises();
    expect(patch).not.toHaveBeenCalled(); expect(card(1).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeDefined();
    expect(card(2).get('[aria-label="Действия с заказом"]').attributes('disabled')).toBeUndefined();
    old.resolve(); await flushPromises();
    expect(card(1)).toBeUndefined(); expect(wrapper.get('nav').text()).toContain('Ожидание 1');
    expect(wrapper.text()).not.toContain('Заказ в ожидании');
  });
  it('invalidates the waiting draft on a filter change and suppresses success after an obsolete updated callback', async () => {
    const heldRead = deferred<ManagerOrderBoardPage>(); vi.spyOn(orderWaitingApi, 'command').mockResolvedValue(order(1, { is_on_hold: true }) as any);
    await start(); await button(card(1), 'В ожидание').trigger('click'); await flushPromises();
    await waitingDialog().get('textarea').setValue('Не переносить на другой контекст');
    await wrapper.get('select[aria-label="Подэтап: Работы"]').setValue('needs_schedule'); await flushPromises();
    expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toBeNull();
    await button(card(1), 'В ожидание').trigger('click'); await flushPromises();
    vi.mocked(orderBoardApi.page).mockReturnValueOnce(heldRead.promise);
    await waitingDialog().get('form').trigger('submit'); await flushPromises();
    wrapper.getComponent({ name: 'OrdersToolbar' }).vm.$emit('update:segment', 'all'); await flushPromises();
    heldRead.resolve(page([order(1)])); await flushPromises();
    expect(wrapper.text()).not.toContain('Заказ в ожидании'); expect(wrapper.getComponent(OrderWaitingDialog).props('order')).toBeNull();
  });
});
