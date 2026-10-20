import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrderDetailView from '../src/views/OrderDetailView.vue';
import { api } from '../src/api';
import { canNavigateAway } from '../src/services/unsaved-navigation-guard';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
const prepare = vi.hoisted(() => vi.fn(async () => true));
vi.mock('../src/components/orders/OrderEditDrawer.vue', () => ({ default: {
  name: 'OrderEditDrawer', props: ['modelValue', 'order', 'presentation', 'backLabel'], emits: ['updated', 'deleted', 'reload', 'back'],
  methods: { prepareToLeave: prepare }, template: '<div />',
} }));
let wrapper: VueWrapper | undefined;
beforeEach(() => { window.history.replaceState({}, '', '/manager/orders/477'); vi.spyOn(window, 'scrollTo').mockImplementation(() => {}); prepare.mockResolvedValue(true); });
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); });
const mountView = () => mount(OrderDetailView, { props: { orderId: 477, returnTo: '/manager/orders/kanban?segment=b2b' } });
describe('standalone order page', () => {
  it.each(['missing', 'archived', 'malformed'])('does not silently show another proposal when the link is %s', async kind => {
    window.history.replaceState({}, '', `/manager/orders/477?proposalId=${kind === 'malformed' ? 'bad' : 25}`);
    vi.spyOn(api, 'getManagerOrderDetail').mockResolvedValue({ id: 477, proposals: [
      { id: 24, is_selected: true }, ...(kind === 'archived' ? [{ id: 25, is_archived: true }] : []),
    ] } as any);
    wrapper = mountView(); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain(kind === 'archived' ? 'в архиве' : 'недоступен');
    expect(wrapper.findComponent({ name: 'OrderEditDrawer' }).exists()).toBe(false);
    expect(await canNavigateAway()).toBe(true);
    await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises();
    expect(window.location.search).toBe('');
  });
  it('loads only the requested order and registers the shared save barrier', async () => {
    const load = vi.spyOn(api, 'getManagerOrderDetail').mockResolvedValue({ id: 477 } as any);
    const list = vi.spyOn(api, 'getManagerOrders');
    wrapper = mountView(); await flushPromises();
    expect(load).toHaveBeenCalledExactlyOnceWith(477);
    expect(list).not.toHaveBeenCalled();
    expect(wrapper.getComponent({ name: 'OrderEditDrawer' }).props()).toMatchObject({ order: { id: 477 }, modelValue: true, presentation: 'page' });
    prepare.mockResolvedValue(false);
    expect(await canNavigateAway()).toBe(false);
    prepare.mockResolvedValue(true);
    expect(await canNavigateAway()).toBe(true);
    wrapper.unmount(); wrapper = undefined;
    expect(await canNavigateAway()).toBe(true);
  });
  it('shows a retryable error and lets the user leave an unavailable order', async () => {
    const load = vi.spyOn(api, 'getManagerOrderDetail').mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ id: 477 } as any);
    wrapper = mountView(); await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Не удалось открыть заказ');
    expect(await canNavigateAway()).toBe(true);
    await wrapper.get('[role="alert"] button').trigger('click'); await flushPromises();
    expect(load).toHaveBeenCalledTimes(2);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
  });
  it('does not render an old scoped response after the selected company changes', async () => {
    let resolve!: (order: any) => void;
    vi.spyOn(api, 'getManagerOrderDetail').mockReturnValueOnce(new Promise(done => { resolve = done; })).mockRejectedValueOnce(new Error('Access denied'));
    wrapper = mountView();
    managerStorefrontSelection.selectedSlug.value = 'different-company';
    resolve({ id: 477, title: 'Old company' }); await flushPromises();
    expect(wrapper.getComponent({ name: 'OrderEditDrawer' }).props('order')).toBeNull();
  });
});
