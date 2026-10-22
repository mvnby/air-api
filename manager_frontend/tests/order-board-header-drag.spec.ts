import { defineComponent, h, nextTick, ref } from 'vue';
import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import KitlaneShell from '../src/components/kitlane/KitlaneShell.vue';
import ManagerContextHeader from '../src/components/manager/ManagerContextHeader.vue';
import ManagerAccountMenu from '../src/components/manager/ManagerAccountMenu.vue';
import OrdersDashboard from '../src/components/orders/OrdersDashboard.vue';
import OrderQueueBoard from '../src/components/orders/OrderQueueBoard.vue';
import OrderCardB2B from '../src/components/orders/OrderCardB2B.vue';
import UiFeedbackHost from '../src/components/common/UiFeedbackHost.vue';
import { orderBoardApi } from '../src/services/order-board';
import { managerSession } from '../src/services/manager-session';
import { api } from '../src/api';
import { resetUiFeedbackForTests } from '../src/services/ui-feedback';
import type { ManagerOrderBoardPage, ManagerOrderListItemResponse } from '../src/client';

const auth = () => ({ username: 'staff', display_name: 'Очень длинное имя ответственного менеджера', tenant_id: 1, staff_user_id: 1 }) as any;
const order = (id: number, status: string) => ({ id, status, title: `Заказ ${id}`, balance_due: 0, total_amount: 100, workflow_revision: 1, customer: { id, type: 'company', name: `Клиент ${id}` } }) as ManagerOrderListItemResponse;
let rows: ManagerOrderListItemResponse[], wrapper: VueWrapper;
const showOrders = ref(true), theme = ref<'light' | 'dark'>('light');
const page = (items: ManagerOrderListItemResponse[]): ManagerOrderBoardPage => ({ items, groups: [], total: items.length, total_orders: items.length, page: 1, limit: 25, has_more: false,
  queue_counts: { active: rows.filter(o => o.status !== 'closed').length, waiting: 0, history: rows.filter(o => o.status === 'closed').length }, work_counts: { all: 2, followup: 0, planning: 1, unpaid: 0 } });
const Host = defineComponent({ setup: () => () => managerSession.auth.value ? h(KitlaneShell, { name: 'Демо', contextKey: 'test', collapsed: false, mobileOpen: false, theme: theme.value,
  onToggleTheme: () => theme.value = theme.value === 'light' ? 'dark' : 'light' }, {
  account: () => h(ManagerAccountMenu, { auth: managerSession.auth.value! }),
  default: () => [showOrders.value ? h(OrdersDashboard) : h('div', { 'data-testid': 'home' }, 'Существующая главная'), h(UiFeedbackHost)],
}) : h('div', { 'data-testid': 'login' }, 'Вход') });
const start = async () => { wrapper = mount(Host, { attachTo: document.body }); await flushPromises(); };
const board = () => wrapper.getComponent(OrderQueueBoard);
const card = (id: number) => wrapper.findAllComponents(OrderCardB2B).find(c => c.props('order').id === id)!;
const target = (key: string) => wrapper.get(key.startsWith('closed_') ? `[data-drop-status="${key}"]` : `[data-drop-column="${key}"]`);
const dialog = () => new DOMWrapper(document.querySelector('[aria-labelledby="ui-dialog-title"]')!);
const button = (root: VueWrapper | DOMWrapper<Element>, label: string) => root.findAll('button').find(b => b.text() === label)!;
const event = async (node: Element, type: string, relatedTarget: Node | null = null) => {
  const transfer = { dropEffect: 'none' };
  const e = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperties(e, { dataTransfer: { value: transfer }, relatedTarget: { value: relatedTarget }, _vts: { value: Date.now() + 1 } });
  node.dispatchEvent(e); await nextTick(); return { e, transfer };
};
const begin = async (id = 1) => { await card(id).get('article').trigger('dragstart'); await nextTick(); };
const active = () => wrapper.findAll('[data-drop-active="true"]');
beforeEach(() => {
  vi.useFakeTimers(); localStorage.clear(); resetUiFeedbackForTests(); showOrders.value = true; theme.value = 'light';
  managerSession.auth.value = auth(); rows = [order(1, 'negotiation'), order(2, 'execution')];
  window.history.replaceState({}, '', '/manager/orders?segment=b2b&groupBy=none');
  vi.spyOn(window, 'scrollTo').mockImplementation(() => {});
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(0), 16));
  vi.stubGlobal('cancelAnimationFrame', (id: number) => clearTimeout(id));
  vi.spyOn(orderBoardApi, 'page').mockImplementation(async q => page(structuredClone(rows.filter(o => o.status !== 'closed' && (!q.column || o.status === q.column)))));
  vi.spyOn(api, 'patchManagerOrder').mockImplementation(async (id, payload) => { Object.assign(rows.find(o => o.id === id)!, payload); return structuredClone(rows.find(o => o.id === id)!) as any; });
});
afterEach(() => { wrapper?.unmount(); resetUiFeedbackForTests(); managerSession.auth.value = null; vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); });

describe('context header owned by the current page', () => {
  it('puts queues, always visible segments and search in the shell, with no second page toolbar', async () => {
    await start(); const header = wrapper.get('.kitlane-topbar');
    expect(header.classes()).toContain('has-context-header');
    expect(header.get('nav[aria-label="Очереди заказов"]').exists()).toBe(true);
    expect(header.get('button[title="Юридические лица"]').isVisible()).toBe(true);
    expect(header.get('button[title="Частные клиенты"]').isVisible()).toBe(true);
    expect(wrapper.get('.orders-queue-page').find('.orders-toolbar').exists()).toBe(false);
    expect(header.get('#orders-options').isVisible()).toBe(false);
    await header.get('button[title="Частные клиенты"]').trigger('click'); await flushPromises();
    expect(orderBoardApi.page).toHaveBeenLastCalledWith(expect.objectContaining({ segment: 'b2c', limit: 25 }));
    expect(header.get('button[title="Частные клиенты"]').attributes('aria-pressed')).toBe('true');
  });
  it('keeps search focus and account/theme interactions, closing the filter panel on account click', async () => {
    await start(); const search = wrapper.get('button[aria-label="Поиск и фильтры"]');
    await search.trigger('click'); await flushPromises();
    expect(document.activeElement).toBe(wrapper.get('input[aria-label="Поиск заказов"]').element);
    const account = wrapper.get('button[aria-label^="Аккаунт:"]'); await account.trigger('click'); await flushPromises();
    expect(wrapper.get('#orders-options').isVisible()).toBe(false); expect(wrapper.get('[role="menu"]').isVisible()).toBe(true);
    await account.trigger('keydown', { key: 'Escape' }); await flushPromises();
    expect(wrapper.get('[role="menu"]').isVisible()).toBe(false);
    await wrapper.get('button[aria-label="Тёмная тема"]').trigger('click'); expect(theme.value).toBe('dark');
    const controls = wrapper.get('.kitlane-topbar').findAll('button');
    expect(controls.findIndex(b => b.attributes('title') === 'Юридические лица')).toBeLessThan(controls.findIndex(b => b.attributes('aria-label')?.startsWith('Аккаунт:')));
  });
  it('removes context controls on leaving orders and registers one fresh header after auth restoration', async () => {
    await start(); showOrders.value = false; await flushPromises();
    expect(wrapper.get('.kitlane-topbar').classes()).not.toContain('has-context-header');
    expect(wrapper.find('nav[aria-label="Очереди заказов"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="home"]').text()).toBe('Существующая главная');
    expect(wrapper.get('button[aria-label="Тёмная тема"]').exists()).toBe(true);
    showOrders.value = true; await flushPromises();
    managerSession.auth.value = null; await flushPromises(); expect(wrapper.find('[data-testid="login"]').exists()).toBe(true); expect(document.querySelectorAll('.orders-toolbar')).toHaveLength(0);
    managerSession.auth.value = { ...auth(), tenant_id: 2 }; await flushPromises();
    expect(wrapper.findAll('nav[aria-label="Очереди заказов"]')).toHaveLength(1);
    expect(wrapper.findAll('.orders-toolbar')).toHaveLength(1);
  });
  it('measures a separate sticky offset without changing the sidebar header variable', async () => {
    let resized!: () => void; const disconnect = vi.fn();
    vi.stubGlobal('ResizeObserver', class { constructor(callback: () => void) { resized = callback; } observe() {} disconnect = disconnect; });
    await start(); vi.spyOn(wrapper.get('.kitlane-topbar').element, 'getBoundingClientRect').mockReturnValue({ height: 132 } as DOMRect);
    resized(); await nextTick();
    expect((wrapper.get('main').element as HTMLElement).style.getPropertyValue('--kitlane-sticky-header-height')).toBe('132px');
    expect((wrapper.get('main').element as HTMLElement).style.getPropertyValue('--kitlane-header-height')).toBe('');
    wrapper.unmount(); expect(disconnect).toHaveBeenCalledOnce();
  });
  it('renders an inline fallback outside a shell without sharing state between independent shells', async () => {
    const fallback = mount(ManagerContextHeader, { slots: { default: '<button>Локальные действия</button>' } });
    expect(fallback.get('.is-inline').text()).toBe('Локальные действия'); fallback.unmount();
    await start(); const other = mount(KitlaneShell, { props: { name: 'Другой', contextKey: 'other', collapsed: false, mobileOpen: false, theme: 'light' } });
    expect(other.get('.kitlane-topbar').classes()).not.toContain('has-context-header'); other.unmount();
  });
});

describe('shared, non-mutating drag hover', () => {
  it('highlights an allowed column and keeps it through nested child boundaries before clearing outside', async () => {
    await start(); await begin(); const column = target('execution');
    await event(column.element, 'dragenter'); await event(column.get('h2').element, 'dragenter');
    await event(column.get('h2').element, 'dragleave', column.get('.queue-scroll').element);
    await event(column.get('.queue-scroll').element, 'dragenter'); await vi.advanceTimersByTimeAsync(20);
    expect(column.attributes('data-drop-active')).toBe('true'); expect(column.classes()).toContain('is-drop-target');
    expect(column.get('h2').text()).toContain('↓Перенести в работы'); expect(api.patchManagerOrder).not.toHaveBeenCalled();
    await event(column.element, 'dragleave', document.body); await vi.advanceTimersByTimeAsync(20);
    expect(active()).toHaveLength(0); expect(api.patchManagerOrder).not.toHaveBeenCalled();
  });
  it('coalesces null-relatedTarget child transitions without a one-frame highlight gap', async () => {
    await start(); await begin(); const column = target('execution');
    await event(column.element, 'dragenter'); await event(column.get('h2').element, 'dragenter');
    await event(column.get('.queue-scroll').element, 'dragenter'); await event(column.get('h2').element, 'dragleave');
    await vi.advanceTimersByTimeAsync(20); expect(column.attributes('data-drop-active')).toBe('true');
    await event(column.get('.queue-scroll').element, 'dragleave'); await event(column.element, 'dragleave');
    await vi.advanceTimersByTimeAsync(20); expect(active()).toHaveLength(0);
  });
  it('does not promise a move to the current status or for an unrelated external drag', async () => {
    await start(); await event(target('execution').element, 'dragenter'); expect(active()).toHaveLength(0);
    await begin(); const current = target('negotiation'); const result = await event(current.element, 'dragover');
    expect(result.transfer.dropEffect).toBe('none'); expect(current.attributes('data-drop-allowed')).toBe('false');
    expect(current.get('h2').text()).toBe('Переговоры 1'); expect(active()).toHaveLength(0);
    await event(current.element, 'drop'); await flushPromises(); expect(api.patchManagerOrder).not.toHaveBeenCalled();
  });
  it.each([[1, 'execution'], [2, 'negotiation']] as const)('drops order %i into %s once and clears all targets', async (id, destination) => {
    await start(); await begin(id); await event(target(destination).element, 'dragover');
    expect(target(destination).attributes('data-drop-active')).toBe('true');
    await event(target(destination).element, 'drop'); await flushPromises();
    expect(api.patchManagerOrder).toHaveBeenCalledExactlyOnceWith(id, expect.objectContaining({ status: destination }));
    expect(active()).toHaveLength(0); expect(wrapper.find('[data-drop-status]').exists()).toBe(false);
  });
  it('shows a strong refusal target in the global header, then keeps cancellation non-mutating', async () => {
    await start(); await begin(); const refusal = target('closed_lost');
    expect(wrapper.get('.kitlane-topbar').find('[data-drop-status="closed_lost"]').exists()).toBe(true);
    await event(refusal.element, 'dragenter'); expect(refusal.attributes('data-drop-active')).toBe('true'); expect(refusal.text()).toContain('↓ Отпустить: отказ');
    await event(refusal.element, 'drop'); await flushPromises(); expect(active()).toHaveLength(0);
    await dialog().get('textarea').setValue('Не сохранять'); await button(dialog(), 'Отмена').trigger('click'); await flushPromises();
    expect(api.patchManagerOrder).not.toHaveBeenCalled(); expect(card(1).props('order').status).toBe('negotiation');
  });
  it('closes an open filter panel when dragging begins, exposing the header targets', async () => {
    await start(); await wrapper.get('button[aria-label="Поиск и фильтры"]').trigger('click'); await flushPromises();
    expect(wrapper.get('#orders-options').isVisible()).toBe(true);
    await begin(); expect(wrapper.get('#orders-options').isVisible()).toBe(false);
    expect(target('closed_lost').isVisible()).toBe(true);
  });
  it('clears the old target when a fresh read changes the source status', async () => {
    await start(); await begin(); await event(target('execution').element, 'dragover');
    rows[0]!.status = 'execution';
    wrapper.getComponent({ name: 'OrdersToolbar' }).vm.$emit('searchNow'); await flushPromises();
    expect(active()).toHaveLength(0); expect(wrapper.find('[data-drop-status]').exists()).toBe(false);
    expect(api.patchManagerOrder).not.toHaveBeenCalled();
  });
  it('blocks dragging a saving order while another order remains available', async () => {
    let resolve!: (result: any) => void;
    vi.mocked(api.patchManagerOrder).mockImplementation(() => new Promise(done => { resolve = done; }));
    await start(); card(1).vm.$emit('renameOrder', { orderId: 1, title: 'Сохраняется' }); await flushPromises();
    await begin(); expect(wrapper.find('[data-drop-status]').exists()).toBe(false);
    await begin(2); await event(target('negotiation').element, 'dragover');
    expect(target('negotiation').attributes('data-drop-active')).toBe('true');
    expect(api.patchManagerOrder).toHaveBeenCalledTimes(1);
    await card(2).get('article').trigger('dragend'); resolve(order(1, 'negotiation')); await flushPromises();
  });
  it('keeps the existing successful completion command behind the success target', async () => {
    await start(); await begin(); const success = target('closed_won'); await event(success.element, 'dragover');
    expect(success.text()).toContain('↓ Отпустить: завершить'); await event(success.element, 'drop'); await flushPromises();
    expect(api.patchManagerOrder).toHaveBeenCalledExactlyOnceWith(1, { status: 'closed', closing_result: 'won', reject_reason: null });
    expect(wrapper.get('nav[aria-label="Очереди заказов"]').text()).toContain('История 1'); expect(active()).toHaveLength(0);
  });
  it.each(['escape', 'dragend', 'outside drop', 'context', 'disabled', 'tenant'])('clears hover and drag state on %s without a save', async why => {
    await start(); await begin(); await event(target('execution').element, 'dragover'); expect(active()).toHaveLength(1);
    if (why === 'escape') await wrapper.get('.kitlane-topbar').trigger('keydown', { key: 'Escape' });
    if (why === 'dragend') await card(1).get('article').trigger('dragend');
    if (why === 'outside drop') await event(document.body, 'drop');
    if (why === 'context') { await wrapper.get('button[title="Частные клиенты"]').trigger('click'); await flushPromises(); }
    if (why === 'disabled') managerSession.auth.value = { ...auth(), demo_read_only: true };
    if (why === 'tenant') managerSession.auth.value = { ...auth(), tenant_id: 2 };
    await flushPromises(); await vi.advanceTimersByTimeAsync(20);
    expect(active()).toHaveLength(0); expect(wrapper.find('[data-drop-status]').exists()).toBe(false); expect(api.patchManagerOrder).not.toHaveBeenCalled();
  });
});
