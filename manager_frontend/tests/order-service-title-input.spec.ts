import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrderServiceTitleInput from '../src/components/orders/OrderServiceTitleInput.vue';
import type { ManagerQuickTariffResponse, ManagerInstallationStandardTariff } from '../src/client';

const mocks = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock('../src/api', () => ({ api: { listManagerQuickTariffs: mocks.list } }));
const tariff: ManagerQuickTariffResponse = { tariff_id: 91, service_kind: 'installation',
  short_name: 'Монтаж', title: 'Монтаж', full_description: 'Трасса 3 м', price: '600',
  category: 'Монтаж', included_route_meters: 3 };
const standard: ManagerInstallationStandardTariff = { code: 'wall.small', title: 'Монтаж до 4,2 кВт',
  description: 'Трасса 3 м; стена до 80 см', price: '600', product_kind: 'complete_split_system',
  indoor_type: 'wall', route_m: '3', holes_by_type: { through_thick: '1' } };
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
const mounted: VueWrapper[] = [];
const mountInput = (value = '', suggestions?: Array<{ tariff: ManagerInstallationStandardTariff; quantity: number }>) => {
  const wrapper = mount(OrderServiceTitleInput, { props: { modelValue: value, workflow: 'sales_installation',
    suggestions, 'onUpdate:modelValue': (next: string) => wrapper.setProps({ modelValue: next }) } });
  mounted.push(wrapper);
  return wrapper;
};
beforeEach(() => { vi.useFakeTimers(); mocks.list.mockReset().mockResolvedValue({ items: [tariff] }); });
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); vi.useRealTimers(); });

describe('inline service title suggestions', () => {
  it('opens suggestions and category buttons on empty focus without a dialog', async () => {
    const wrapper = mountInput();
    expect(wrapper.find('[data-testid="service-context-menu"]').exists()).toBe(false);
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    expect(mocks.list).toHaveBeenCalledWith('', null, 100);
    expect(wrapper.get('[role="group"]').text()).toContain('Монтаж');
    expect(wrapper.get('[role="group"]').text()).toContain('Обслуживание');
    expect(wrapper.get('[data-testid="select-service-91"]').text()).toContain('600 BYN');
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);
  });

  it('searches a single character and filters by category while retaining arbitrary typed text', async () => {
    const wrapper = mountInput();
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    await wrapper.get('textarea').setValue('М');
    await vi.advanceTimersByTimeAsync(200);
    expect(mocks.list).toHaveBeenLastCalledWith('М', null, 100);
    const maintenance = wrapper.findAll('[role="group"] button').find((button) => button.text() === 'Обслуживание')!;
    await maintenance.trigger('click');
    await flushPromises();
    expect(mocks.list).toHaveBeenLastCalledWith('', 'maintenance', 100);
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('М');
    expect(maintenance.attributes('aria-pressed')).toBe('true');
    await wrapper.get('textarea').setValue('Обс');
    await vi.advanceTimersByTimeAsync(200);
    expect(mocks.list).toHaveBeenLastCalledWith('Обс', 'maintenance', 100);
    await maintenance.trigger('click');
    expect(mocks.list).toHaveBeenLastCalledWith('Обс', null, 100);
  });

  it.each(['empty', 'failure'])('allows a manually written title when lookup returns %s', async (state) => {
    if (state === 'failure') mocks.list.mockRejectedValue(new Error('offline'));
    else mocks.list.mockResolvedValue({ items: [] });
    const wrapper = mountInput('Особая работа по согласованию');
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    expect(wrapper.text()).toContain(state === 'failure' ? 'Можно заполнить услугу вручную' : 'Оставьте своё название');
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Особая работа по согласованию');
    expect(wrapper.get('textarea').attributes('disabled')).toBeUndefined();
    expect(wrapper.emitted('select')).toBeUndefined();
  });

  it('uses Arrow and Enter to choose a tariff and Escape to close suggestions', async () => {
    const wrapper = mountInput();
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    await wrapper.get('textarea').trigger('keydown', { key: 'ArrowDown' });
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter' });
    expect(wrapper.emitted('select')?.[0]?.[0]).toEqual(tariff);
    expect(wrapper.find('[data-testid="service-context-menu"]').exists()).toBe(false);
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    await wrapper.get('textarea').trigger('keydown', { key: 'Escape' });
    expect(wrapper.get('textarea').attributes('aria-expanded')).toBe('false');
    expect(wrapper.emitted('select')).toHaveLength(1);
  });

  it('keeps category navigation inside the inline menu and reopens after Escape', async () => {
    const wrapper = mountInput('Работа');
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    const category = wrapper.findAll('[role="group"] button')[0]!;
    await wrapper.get('textarea').trigger('focusout', { relatedTarget: category.element });
    expect(wrapper.find('[data-testid="service-context-menu"]').exists()).toBe(true);
    expect(wrapper.emitted('blur')).toBeUndefined();
    await category.trigger('click');
    await flushPromises();
    expect(mocks.list).toHaveBeenLastCalledWith('', 'installation', 100);
    await wrapper.get('textarea').trigger('keydown', { key: 'Escape' });
    expect(wrapper.find('[data-testid="service-context-menu"]').exists()).toBe(false);
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    expect(wrapper.find('[data-testid="service-context-menu"]').exists()).toBe(true);
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('Работа');
    expect(wrapper.get('[data-testid="select-service-91"]').exists()).toBe(true);
  });

  it('ignores results from the previous category when the new category has already loaded', async () => {
    const previous = deferred<{ items: ManagerQuickTariffResponse[] }>();
    mocks.list.mockReturnValueOnce(previous.promise).mockResolvedValue({ items: [] });
    const wrapper = mountInput('Работа');
    await wrapper.get('textarea').trigger('focus');
    await wrapper.findAll('[role="group"] button').find((item) => item.text() === 'Ремонт')!.trigger('click');
    await flushPromises();
    previous.resolve({ items: [tariff] });
    await flushPromises();
    expect(wrapper.find('[data-testid="select-service-91"]').exists()).toBe(false);
    expect(mocks.list).toHaveBeenLastCalledWith('', 'repair', 100);
  });

  it('offers published standards as ordinary choices and supplies current quantity only for product recommendations', async () => {
    mocks.list.mockResolvedValue({ items: [{ ...tariff, tariff_id: null, installation_standard: standard,
      title: standard.title, short_name: standard.title, price: standard.price }] });
    const wrapper = mountInput('', [{ tariff: standard, quantity: 27 }]);
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    await wrapper.get('[data-testid="select-service-wall.small"]').trigger('click');
    expect(wrapper.emitted('select')?.[0]?.[1]).toBeUndefined();
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    const recommendation = wrapper.findAll('button').find((button) => button.text().includes('27 шт.'))!;
    await recommendation.trigger('click');
    expect(wrapper.emitted('select')?.[1]).toEqual([expect.objectContaining({
      tariff_id: null, installation_standard: standard }), 27]);
  });

  it('ignores an old query response immediately after new input, even before debounce finishes', async () => {
    const old = deferred<{ items: ManagerQuickTariffResponse[] }>();
    mocks.list.mockReturnValueOnce(old.promise).mockResolvedValue({ items: [] });
    const wrapper = mountInput();
    await wrapper.get('textarea').trigger('focus');
    await wrapper.get('textarea').setValue('Новое название');
    old.resolve({ items: [tariff] });
    await flushPromises();
    expect(wrapper.find('[data-testid="select-service-91"]').exists()).toBe(false);
    await vi.advanceTimersByTimeAsync(200);
    expect(mocks.list).toHaveBeenLastCalledWith('Новое название', null, 100);
  });

  it('does not restore stale results after choosing a recommendation or unmounting', async () => {
    const old = deferred<{ items: ManagerQuickTariffResponse[] }>();
    mocks.list.mockReturnValueOnce(old.promise).mockResolvedValue({ items: [] });
    const wrapper = mountInput('', [{ tariff: standard, quantity: 2 }]);
    await wrapper.get('textarea').trigger('focus');
    await wrapper.findAll('button').find((button) => button.text().includes('2 шт.'))!.trigger('click');
    old.resolve({ items: [tariff] });
    await flushPromises();
    await wrapper.get('textarea').trigger('focus');
    await flushPromises();
    expect(wrapper.find('[data-testid="select-service-91"]').exists()).toBe(false);
    const pending = deferred<{ items: ManagerQuickTariffResponse[] }>();
    mocks.list.mockReturnValueOnce(pending.promise);
    await wrapper.get('textarea').setValue('После выбора');
    await vi.advanceTimersByTimeAsync(200);
    const onSelect = vi.fn();
    await wrapper.setProps({ onSelect });
    wrapper.unmount();
    mounted.splice(mounted.indexOf(wrapper), 1);
    pending.resolve({ items: [tariff] });
    await flushPromises();
    expect(onSelect).not.toHaveBeenCalled();
  });
});
