import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../src/api';
import CreateOrderModal from '../src/components/CreateOrderModal.vue';

const wrappers: VueWrapper[] = [];
const scenarios = {
  items: [
    { label: 'Обслуживание', workflow_type: 'maintenance', service_type: 'maintenance', hint: '' },
    { label: 'Работы', workflow_type: 'service_work', service_type: null, hint: '' },
  ],
};

const mountModal = () => {
  const wrapper = mount(CreateOrderModal, {
    props: { customerId: 42, customerName: 'ООО Пример' },
    global: { stubs: { teleport: true, transition: false } },
  });
  wrappers.push(wrapper);
  return wrapper;
};

beforeEach(() => {
  vi.spyOn(api, 'getManagerOrderScenarios').mockResolvedValue(scenarios);
  vi.spyOn(api, 'getManagerCustomerBranches').mockResolvedValue({ items: [] } as never);
  vi.spyOn(api, 'createManagerOrder').mockResolvedValue({ id: 123 } as never);
});

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
});

describe('CreateOrderModal scenarios', () => {
  it('creates maintenance for the selected customer with no invented description or date', async () => {
    const wrapper = mountModal();
    await flushPromises();
    expect(wrapper.findAll('button').find((button) => button.text() === 'Создать заказ')?.attributes('disabled')).toBeDefined();

    await wrapper.findAll('button').find((button) => button.text() === 'Обслуживание')!.trigger('click');
    await wrapper.findAll('button').find((button) => button.text() === 'Создать заказ')!.trigger('click');
    await flushPromises();

    expect(api.createManagerOrder).toHaveBeenCalledWith(expect.objectContaining({
      customer_id: 42,
      workflow_type: 'maintenance',
      service_type: 'maintenance',
      request_text: '',
      target_date: null,
      address: null,
    }));
    expect(wrapper.emitted('created')?.[0]).toEqual([123]);
  });

  it('reuses the creation key on retry and sends a generic work scenario without a stale service type', async () => {
    vi.mocked(api.createManagerOrder).mockRejectedValueOnce(new Error('temporary')).mockResolvedValueOnce({ id: 124 } as never);
    const wrapper = mountModal();
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text() === 'Работы')!.trigger('click');
    const submit = () => wrapper.findAll('button').find((button) => button.text() === 'Создать заказ')!;
    await submit().trigger('click');
    await flushPromises();
    await submit().trigger('click');
    await flushPromises();

    const calls = vi.mocked(api.createManagerOrder).mock.calls.map(([payload]) => payload);
    expect(calls).toHaveLength(2);
    expect(calls[0].client_request_id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(calls[1].client_request_id).toBe(calls[0].client_request_id);
    expect(calls[1]).toEqual(expect.objectContaining({
      workflow_type: 'service_work',
      service_type: null,
    }));
  });
});
