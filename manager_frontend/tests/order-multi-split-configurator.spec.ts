import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderMultiSplitConfigurator from '../src/components/orders/OrderMultiSplitConfigurator.vue';

const service = vi.hoisted(() => ({
  options: vi.fn(),
  preview: vi.fn(),
  save: vi.fn(),
}));
vi.mock('../src/client', () => ({ ManagerMultiSplitService: {
  listManagerMultiSplitOptions: service.options,
  previewManagerMultiSplit: service.preview,
  saveManagerMultiSplitProposal: service.save,
} }));

const components = [
  { product_id: 1, title: 'Наружный', product_kind: 'outdoor_unit', quantity: 1, unit_price_byn: 2000, total_price_byn: 2000, availability: 'in_stock_now' },
  { product_id: 2, title: 'Внутренний', product_kind: 'indoor_unit', quantity: 1, unit_price_byn: 800, total_price_byn: 800, availability: 'in_stock_now' },
];

beforeEach(() => {
  vi.clearAllMocks();
  service.options.mockImplementation(async (kind: string) => ({
    items: [{ id: kind === 'outdoor_unit' ? 1 : 2, title: kind === 'outdoor_unit' ? 'Наружный' : 'Внутренний', slug: kind, product_kind: kind, price_byn: kind === 'outdoor_unit' ? 2000 : 800, availability: 'in_stock_now' }],
    meta: { page: 1, limit: 100, total: 1, pages: 1 },
  }));
  service.preview.mockResolvedValue({ status: 'requires_specialist', explanation: 'Нужна проверка', composition_complete: false, equipment_total_byn: 2800, components, purchase_cost_total_byn: 1900, margin_byn: 900 });
  service.save.mockResolvedValue({ id: 8, proposals: [] });
});

describe('OrderMultiSplitConfigurator', () => {
  it('uses the server preview and saves all components as one alternative', async () => {
    const beforeSave = vi.fn().mockResolvedValue(true);
    const wrapper = mount(OrderMultiSplitConfigurator, { props: { orderId: 8, proposals: [], beforeSave } });
    await flushPromises();
    await wrapper.get('[data-testid="multi-outdoor"]').setValue('1');
    await wrapper.findAll('select').find((select) => select.html().includes('Внутренний'))?.setValue('2');
    await wrapper.findAll('button').find((button) => button.text().includes('Пересчитать'))?.trigger('click');
    await flushPromises();

    expect(service.preview).toHaveBeenCalledWith({ outdoor_product_id: 1, rooms: [{ name: 'Помещение 1', indoor_product_id: 2 }] });
    expect(wrapper.get('[data-testid="multi-preview"]').text()).toContain('Требуется проверка специалистом');
    expect(wrapper.get('[data-testid="multi-preview"]').text()).toContain('Оборудование:');
    await wrapper.findAll('button').find((button) => button.text().includes('Сохранить отдельным'))?.trigger('click');
    await flushPromises();
    expect(beforeSave).toHaveBeenCalledOnce();
    expect(service.save).toHaveBeenCalledWith(8, expect.objectContaining({
      outdoor_product_id: 1,
      expected_status: 'requires_specialist',
      expected_components: components,
    }));
    expect(wrapper.emitted('updated')).toHaveLength(1);
  });
});
