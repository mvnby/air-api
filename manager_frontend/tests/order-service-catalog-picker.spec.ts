import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderServiceCatalogPicker from '../src/components/orders/OrderServiceCatalogPicker.vue';
import { orderedServiceKinds, serviceCategories } from '../src/components/orders/service-catalog-order';

const apiMocks = vi.hoisted(() => ({
  listManagerTariffsByKind: vi.fn(),
  listManagerInstallationRates: vi.fn(),
  calculateManagerInstallEstimate: vi.fn(),
  createManagerServiceEstimate: vi.fn(),
  getManagerServiceEstimateOrderLines: vi.fn(),
}));
vi.mock('../src/api', () => ({ api: apiMocks }));

const tariff = {
  id: 21,
  service_kind: 'installation',
  short_name: 'Монтаж настенного блока',
  full_description: 'Монтаж с трассой до 3 м',
  selector_label: 'Монтаж настенного блока',
  estimate_template: 'Монтаж настенного блока',
  category: 'Настенные',
  power_range: 'до 4 кВт',
  base_price: 300,
  included_route_meters: 3,
  is_active: true,
  sort_order: 1,
  rules: [
    { id: 31, tariff_id: 21, rule_type: 'per_meter_over_included', name: 'Доп. трасса', line_template: '{name}', unit: 'м', unit_price: 20, is_optional: false, is_active: true, sort_order: 1 },
    { id: 32, tariff_id: 21, rule_type: 'fixed_once', name: 'Дренажный насос', line_template: '{name}', unit: 'шт', unit_price: 90, is_optional: true, is_active: true, sort_order: 2 },
  ],
} as const;

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.listManagerTariffsByKind.mockResolvedValue({ items: [tariff] });
  apiMocks.listManagerInstallationRates.mockResolvedValue({ published_price_book_revision: null, items: [] });
  apiMocks.calculateManagerInstallEstimate.mockResolvedValue({ total: 410, currency: 'BYN', lines: [{ name: 'Монтаж', line_total: 300 }], rule_lines: [] });
  apiMocks.createManagerServiceEstimate.mockResolvedValue({ id: 84 });
  apiMocks.getManagerServiceEstimateOrderLines.mockResolvedValue({ services: [{ title: 'Монтаж', quantity: 1, price: 410, service_id: 9 }] });
});

describe('OrderServiceCatalogPicker', () => {
  it('puts the workflow direction first and groups real tariff categories', () => {
    expect(orderedServiceKinds('maintenance')[0]?.value).toBe('maintenance');
    expect(orderedServiceKinds('sales_installation')[0]?.value).toBe('installation');
    expect(serviceCategories([tariff as any], 'installation')).toEqual(['Настенные']);
  });

  it('lets a manager browse and add a known service without typing its name', async () => {
    const wrapper = mount(OrderServiceCatalogPicker, { props: { workflow: 'sales_installation' } });
    await flushPromises();
    expect(wrapper.text()).toContain('Монтаж настенного блока');
    expect(wrapper.text()).toContain('Настенные');
    await wrapper.findAll('button').find((button) => button.text() === 'Добавить')!.trigger('click');
    await flushPromises();
    expect(wrapper.emitted('choose')?.[0]?.[0]).toMatchObject({ tariff_id: 21, price: 300 });
    wrapper.unmount();
  });

  it('calculates, saves and imports a new estimate into the order', async () => {
    const wrapper = mount(OrderServiceCatalogPicker, { props: { workflow: 'sales_installation', customerId: 12 } });
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text() === 'Собрать смету')!.trigger('click');
    await flushPromises();
    const inputs = wrapper.findAll('input[type="number"]');
    await inputs[0]!.setValue(5);
    await inputs[3]!.setValue(1);
    await wrapper.findAll('button').find((button) => button.text() === 'Рассчитать смету')!.trigger('click');
    await flushPromises();
    expect(apiMocks.calculateManagerInstallEstimate).toHaveBeenCalledWith(expect.objectContaining({
      tariff_id: 21,
      route_length_m: 5,
      rule_inputs: [{ rule_id: 32, qty: 1 }],
    }));
    await wrapper.findAll('button').find((button) => button.text() === 'Сохранить смету и добавить в заказ')!.trigger('click');
    await flushPromises();
    expect(apiMocks.createManagerServiceEstimate).toHaveBeenCalledWith(expect.objectContaining({ customer_id: 12 }));
    expect(wrapper.emitted('createdEstimate')?.[0]?.[0]).toMatchObject({ id: 84, lines: [{ title: 'Монтаж', price: 410 }] });
    wrapper.unmount();
  });

  it('hides typed installation quick-add and opens the order price-book panel after publication', async () => {
    apiMocks.listManagerInstallationRates.mockResolvedValue({ published_price_book_revision: 2, items: [] });
    const wrapper = mount(OrderServiceCatalogPicker, { props: { workflow: 'sales_installation', canOpenInstallationEstimate: true } });
    await flushPromises();
    expect(wrapper.text()).toContain('Монтаж рассчитывается по опубликованной книге цен');
    expect(wrapper.findAll('button').some((button) => button.text() === 'Добавить')).toBe(false);
    expect(wrapper.findAll('button').some((button) => button.text() === 'Собрать смету')).toBe(false);
    await wrapper.findAll('button').find((button) => button.text() === 'Открыть расчёт монтажа')!.trigger('click');
    expect(wrapper.emitted('openInstallationEstimate')).toEqual([[]]);
    wrapper.unmount();
  });
});
