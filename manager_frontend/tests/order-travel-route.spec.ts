import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OrderTravelRoute from '../src/components/orders/OrderTravelRoute.vue';
import { ApiError, CancelablePromise } from '../src/client';
import type { ManagerOrderTravelRouteResponse } from '../src/client';

const calculate = vi.hoisted(() => vi.fn());
vi.mock('../src/client', async original => ({
  ...(await original<typeof import('../src/client')>()),
  ManagerOrdersService: { calculateManagerOrderTravelRoute: calculate },
}));

const route: ManagerOrderTravelRouteResponse = {
  provider: 'openrouteservice',
  origin: 'Витебск, центр города',
  destination: 'Беларусь, Ушачи',
  approximate_destination: true,
  outbound: { distance_m: 117000, duration_s: 5400 },
  inbound: { distance_m: 118300, duration_s: 6000 },
  total: { distance_m: 235300, duration_s: 11400 },
};
afterEach(() => calculate.mockReset());

describe('OrderTravelRoute', () => {
  it('requests both directions on demand for the draft address and displays a round trip', async () => {
    calculate.mockReturnValue(new CancelablePromise(resolve => resolve(route)));
    const wrapper = mount(OrderTravelRoute, { props: { orderId: 699, address: '  Ушачи  ' } });
    try {
      expect(calculate).not.toHaveBeenCalled();
      const url = new URL(wrapper.get('a').attributes('href'));
      expect(url.searchParams.get('origin')).toBe(url.searchParams.get('destination'));
      expect(url.searchParams.get('waypoints')).toBe('Беларусь, Ушачи');
      await wrapper.get('button').trigger('click');
      await flushPromises();
      expect(calculate).toHaveBeenCalledOnce();
      expect(calculate).toHaveBeenCalledWith(699, { address: 'Ушачи' });
      expect(wrapper.text()).toContain('3 ч 10 мин');
      expect(wrapper.text()).toContain('235,3 км');
      expect(wrapper.text()).toContain('До центра населённого пункта');
      expect(wrapper.text()).toContain('© openrouteservice.org by HeiGIT');
    } finally { wrapper.unmount(); }
  });

  it('clears a stale route when the address changes during calculation', async () => {
    const cancel = vi.fn();
    calculate.mockReturnValue(new CancelablePromise((_, __, onCancel) => onCancel(cancel)));
    const wrapper = mount(OrderTravelRoute, { props: { orderId: 699, address: 'Ушачи' } });
    try {
      await wrapper.get('button').trigger('click');
      await wrapper.setProps({ address: 'Лепель' });
      await flushPromises();
      expect(cancel).toHaveBeenCalledOnce();
      expect(wrapper.find('[disabled]').exists()).toBe(false);
      expect(wrapper.text()).not.toContain('Ушачи');
      expect(wrapper.text()).not.toContain('Маршрут сейчас недоступен');
    } finally { wrapper.unmount(); }
  });

  it('keeps the navigator available when the provider is unconfigured', async () => {
    calculate.mockReturnValue(new CancelablePromise((_, reject) => reject(new ApiError(
      { method: 'POST', url: '/api/manager/orders/699/travel-route' },
      { url: '', ok: false, status: 503, statusText: '', body: { detail: { code: 'order_route_not_configured' } } },
      'Service unavailable',
    ))));
    const wrapper = mount(OrderTravelRoute, { props: { orderId: 699, address: 'Ушачи' } });
    try {
      await wrapper.get('button').trigger('click');
      await flushPromises();
      expect(wrapper.text()).toContain('Расчёт маршрута в Manager пока не подключён');
      expect(wrapper.get('a').attributes('target')).toBe('_blank');
    } finally { wrapper.unmount(); }
  });
});
