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
    wrapper.unmount();
  });
});


describe('multisplit BYN presentation', () => {
  it.each([
    ['zero', 0, '0'], ['negative', -1234.5, '-1 234,5'],
    ['fractional', 1234.567, '1 234,57'], ['large', 123456789.01, '123 456 789,01'],
    ['missing', null, null], ['undefined', undefined, null],
    ['unknown string', 'unknown', null], ['numeric string', '1234.50', null],
    ['NaN', NaN, null], ['Infinity', Infinity, null],
  ])('renders %s in preview and saved totals without changing raw save values', async (_case, value, formatted) => {
    const previewComponents = components.map((part) => ({ ...part, total_price_byn: value }));
    service.preview.mockResolvedValue({ status: 'requires_specialist', explanation: 'Нужна проверка', composition_complete: false,
      equipment_total_byn: value, purchase_cost_total_byn: value, margin_byn: value, components: previewComponents });
    const wrapper = mount(OrderMultiSplitConfigurator, { props: {
      orderId: 8, beforeSave: vi.fn().mockResolvedValue(true),
      proposals: [{ id: 5, name: 'Мультисплит', total_amount: value,
        multi_split_configuration: { rooms: [], component_snapshot: [], verification_status: 'confirmed' } }] as any,
    } });
    try {
      await flushPromises();
      await wrapper.get('[data-testid="multi-outdoor"]').setValue('1');
      await wrapper.findAll('select').find((select) => select.html().includes('Внутренний'))?.setValue('2');
      await wrapper.findAll('button').find((button) => button.text().includes('Пересчитать'))?.trigger('click');
      await flushPromises();
      const preview = wrapper.get('[data-testid="multi-preview"]');
      const saved = wrapper.findAll('p').find((paragraph) => paragraph.text().includes('сохранено'))!;
      if (formatted !== null) {
        const amounts = [...preview.findAll('.inline-flex'), ...saved.findAll('.inline-flex')];
        expect(amounts).toHaveLength(6);
        for (const amount of amounts) {
          expect(amount.text().replace(/\s/g, ' ')).toBe(formatted + ' BYN');
          expect(amount.get('.sr-only').text()).toBe('BYN');
          expect(amount.get('svg').attributes('aria-hidden')).toBe('true');
        }
      } else {
        expect(preview.findAll('svg')).toHaveLength(0);
        expect(preview.text().match(/нет данных/g)).toHaveLength(5);
        expect(saved.text()).toContain('сохранено нет данных');
        expect(saved.findAll('svg')).toHaveLength(0);
      }
      expect(wrapper.get('[data-testid="multi-outdoor"] option:last-child').text()).toBe('Наружный · 2 000 BYN');
      expect(wrapper.findAll('select').find((select) => select.html().includes('Внутренний'))!.find('option:last-child').text()).toBe('Внутренний · 800 BYN · В наличии');
      await wrapper.findAll('button').find((button) => button.text().includes('Сохранить отдельным'))?.trigger('click');
      await flushPromises();
      expect(service.save.mock.calls[0]?.[1].expected_components).toEqual(previewComponents);
    } finally { wrapper.unmount(); }
  });
});
