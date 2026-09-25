import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ServiceEstimatesView from '../src/views/ServiceEstimatesView.vue';

const apiMock = vi.hoisted(() => ({
  listManagerTariffsByKind: vi.fn(),
  listManagerInstallationRates: vi.fn(),
  listManagerServiceEstimates: vi.fn(),
  calculateManagerInstallEstimate: vi.fn(),
  createManagerServiceEstimate: vi.fn(),
  getManagerServiceEstimate: vi.fn(),
  deleteManagerServiceEstimate: vi.fn(),
  getManagerCustomers: vi.fn(),
}));
vi.mock('../src/api', () => ({ api: apiMock }));

const tariff = {
  id: 9, service_kind: 'installation', short_name: 'Монтаж', selector_label: 'Монтаж', full_description: 'Монтаж кондиционера', category: 'Настенные', power_range: 'до 4 кВт', base_price: 300, included_route_meters: 3, is_active: true, sort_order: 1, rules: [],
};
const calculation = {
  tariff, lines: [{ source_type: 'base', sort_order: 1, name: 'Монтаж', qty: 1, unit: 'шт', unit_price: 300, line_total: 300 }], rule_lines: [], subtotal: 300, discount_amount: 0, total: 300, currency: 'BYN',
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMock.listManagerTariffsByKind.mockResolvedValue({ items: [tariff] });
  apiMock.listManagerInstallationRates.mockResolvedValue({ published_price_book_revision: null, items: [] });
  apiMock.listManagerServiceEstimates.mockResolvedValue({ page: 1, limit: 20, total: 1, items: [{ id: 3, title: 'Смета', comment: null, tariff, total: 300, currency: 'BYN', status: 'approved', created_at: '2026-09-23T10:00:00Z', lines: [] }] });
  apiMock.calculateManagerInstallEstimate.mockResolvedValue(calculation);
  apiMock.createManagerServiceEstimate.mockResolvedValue({ id: 4 });
  apiMock.getManagerServiceEstimate.mockResolvedValue({ id: 4, title: 'Смета', tariff, total: 300, currency: 'BYN', status: 'draft', lines: [] });
});

afterEach(() => vi.clearAllMocks());

const mountView = async () => {
  const wrapper = mount(ServiceEstimatesView);
  await flushPromises();
  return wrapper;
};

describe('ServiceEstimatesView', () => {
  it('keeps history but directs new installation estimates to the order after publication', async () => {
    apiMock.listManagerInstallationRates.mockResolvedValue({ published_price_book_revision: 1, items: [] });
    const wrapper = await mountView();
    expect(wrapper.text()).toContain('Согласована');
    expect(wrapper.text()).toContain('Монтаж теперь рассчитывается по опубликованной книге цен');
    expect(wrapper.get('a[href="/manager/orders"]').text()).toContain('Открыть заказы');
    expect(wrapper.findAll('button').some((button) => button.text().includes('Рассчитать смету'))).toBe(false);
    expect(apiMock.calculateManagerInstallEstimate).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('uses Russian status labels and saves a calculation without a customer', async () => {
    const wrapper = await mountView();
    expect(wrapper.text()).toContain('Согласована');
    expect(wrapper.text()).not.toContain('>approved<');

    await wrapper.findAll('button').find((button) => button.text().includes('Рассчитать смету'))!.trigger('click');
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text().includes('Сохранить смету'))!.trigger('click');
    await flushPromises();

    expect(apiMock.createManagerServiceEstimate).toHaveBeenCalledWith(expect.objectContaining({ customer_id: null, status: 'draft' }));
    wrapper.unmount();
  });

  it('keeps the calculated form available after a save error and allows retry', async () => {
    let rejectSave: ((error: Error) => void) | undefined;
    apiMock.createManagerServiceEstimate
      .mockImplementationOnce(() => new Promise((_, reject) => { rejectSave = reject; }));
    const wrapper = await mountView();
    await wrapper.findAll('button').find((button) => button.text().includes('Рассчитать смету'))!.trigger('click');
    await flushPromises();
    const saveButton = () => wrapper.findAll('button').find((button) => button.text().includes('Сохран'))!;
    await saveButton().trigger('click');
    await saveButton().trigger('click');
    expect(apiMock.createManagerServiceEstimate).toHaveBeenCalledTimes(1);
    rejectSave?.(new Error('Сеть недоступна'));
    await flushPromises();

    expect(wrapper.text()).toContain('Сеть недоступна');
    expect(wrapper.text()).toContain('Монтаж');
    await saveButton().trigger('click');
    await flushPromises();
    expect(apiMock.createManagerServiceEstimate).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });

  it('does not save a result after recalculation fails for changed inputs', async () => {
    apiMock.calculateManagerInstallEstimate
      .mockResolvedValueOnce(calculation)
      .mockRejectedValueOnce(new Error('Расчёт недоступен'));
    const wrapper = await mountView();
    await wrapper.findAll('button').find((button) => button.text().includes('Рассчитать смету'))!.trigger('click');
    await flushPromises();
    await wrapper.find('input[type="number"]').setValue(2);
    await flushPromises();

    await wrapper.findAll('button').find((button) => button.text().includes('Рассчитать смету'))!.trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('Расчёт недоступен');
    expect(wrapper.findAll('button').some((button) => button.text().includes('Сохранить смету'))).toBe(false);
    expect(apiMock.createManagerServiceEstimate).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('ignores a calculation response after its inputs change', async () => {
    let resolveCalculation: ((value: typeof calculation) => void) | undefined;
    apiMock.calculateManagerInstallEstimate.mockImplementationOnce(() => new Promise((resolve) => { resolveCalculation = resolve; }));
    const wrapper = await mountView();

    await wrapper.findAll('button').find((button) => button.text().includes('Рассчитать смету'))!.trigger('click');
    await wrapper.find('input[type="number"]').setValue(2);
    resolveCalculation?.(calculation);
    await flushPromises();

    expect(wrapper.findAll('button').some((button) => button.text().includes('Сохранить смету'))).toBe(false);
    expect(apiMock.createManagerServiceEstimate).not.toHaveBeenCalled();
    wrapper.unmount();
  });
});
