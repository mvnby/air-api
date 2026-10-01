import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';
import OrderServiceLinesEditor from '../src/components/orders/OrderServiceLinesEditor.vue';
import ServiceDescriptionModeSwitch from '../src/components/orders/ServiceDescriptionModeSwitch.vue';
import type { ServiceLine } from '../src/components/orders/order-editor-types';
import { managerSession } from '../src/services/manager-session';

const tariff = {
  tariff_id: 91,
  service_kind: 'installation' as const,
  short_name: 'Стандартный монтаж',
  full_description: 'Монтаж с трассой до 3 метров',
  title: 'Стандартный монтаж',
  price: 600,
  category: 'Монтаж',
  included_route_meters: 3,
};

const estimate = {
  id: 81,
  title: 'Смета объекта',
  service_kind: 'installation',
  currency: 'BYN',
  subtotal: 1_000,
  discount_amount: 0,
  total: 1_000,
  status: 'draft',
  created_at: '2026-07-31T10:00:00Z',
};

const baseProps = (lines: ServiceLine[], extra: Record<string, unknown> = {}) => ({
  lines,
  editingIndex: null,
  showEstimateImport: false,
  selectedEstimateId: null,
  estimateSearchQuery: '',
  estimateImportMode: 'collapsed' as const,
  descriptionMode: 'short' as const,
  serviceOptions: [tariff],
  serviceLookupLoading: false,
  activeSuggestionIndex: null,
  estimateOptions: [estimate],
  estimateOptionsLoading: false,
  importingEstimate: false,
  formatServiceKind: () => 'монтаж',
  workflow: 'sales_installation' as const,
  ...extra,
});

const mounted: VueWrapper[] = [];
const mountEditor = (lines: ServiceLine[], extra: Record<string, unknown> = {}) => {
  const wrapper = mount(OrderServiceLinesEditor, { props: baseProps(lines, extra) });
  mounted.push(wrapper);
  return wrapper;
};

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  managerSession.auth.value = null;
});

describe('OrderServiceLinesEditor compact rows', () => {
  it('renders immutable installation snapshots as individual quantity by price rows', () => {
    const frozen: ServiceLine = {
      service_id: null,
      title: 'Установка №1…№5',
      quantity: 1,
      price: 3_000,
      cost: 0,
      installation_estimate_revision_id: 10,
      installation_display_lines: [
        { title: 'Монтаж настенного кондиционера', description: 'Трасса 3 м', quantity: 5, price: 600 },
        { title: 'Дополнительные работы', description: 'Прокладка канала', quantity: 2, price: 150 },
      ],
    };
    const wrapper = mountEditor([frozen], { compact: true });

    expect(wrapper.findAll('[data-testid^="compact-service-row-"]')).toHaveLength(2);
    expect(wrapper.text()).toContain('Монтаж настенного кондиционера');
    expect(wrapper.text()).toContain('5');
    expect(wrapper.get('[data-testid="compact-service-row-0-0"]').text()).toContain('600 BYN');
    expect(wrapper.text()).toContain('3 000 BYN');
    expect(wrapper.text()).toContain('Монтаж зафиксирован');
    expect(wrapper.find('[data-order-usage="order_service_edit"]').exists()).toBe(false);
    expect(wrapper.find('[data-order-usage="order_service_remove"]').exists()).toBe(false);
    expect(wrapper.emitted('update:lines')).toBeUndefined();
    expect(frozen).toMatchObject({ title: 'Установка №1…№5', quantity: 1, price: 3_000 });
  });

  it('opens controls only for the selected ordinary service and keeps its description callback', async () => {
    const lines: ServiceLine[] = [
      { service_id: null, title: 'Первая услуга', quantity: 1, price: 100, cost: 30 },
      { service_id: null, title: 'Вторая услуга', quantity: 2, price: 200, cost: 50,
        template_full_description: 'Полное описание', description_mode: 'short' },
    ];
    const wrapper = mountEditor(lines, { compact: true, editingIndex: 1 });

    expect(wrapper.findAll('textarea')).toHaveLength(1);
    expect(wrapper.findAll('button[data-order-usage="order_service_edit"]')).toHaveLength(1);
    expect(wrapper.get('button[data-order-usage="order_service_edit"]').attributes('aria-label')).toContain('#1');
    await wrapper.getComponent(ServiceDescriptionModeSwitch).get('button[aria-pressed="false"]').trigger('click');
    expect(wrapper.emitted('descriptionMode')).toEqual([[{ index: 1, mode: 'full' }]]);
    expect(wrapper.emitted('remove')).toBeUndefined();
  });

  it('shows compact cost only when requested and permitted', async () => {
    const wrapper = mountEditor([
      { service_id: null, title: 'Монтаж', quantity: 1, price: 600, cost: 250 },
    ], { compact: true, showCosts: false });
    expect(wrapper.text()).not.toContain('250');
    expect(wrapper.text()).not.toContain('Себест.');

    await wrapper.setProps({ showCosts: true });
    expect(wrapper.text()).toContain('250');

    managerSession.auth.value = { demo_read_only: true } as any;
    const demoWrapper = mountEditor([
      { service_id: null, title: 'Монтаж', quantity: 1, price: 600, cost: 250 },
    ], { compact: true, showCosts: true });
    expect(demoWrapper.text()).not.toContain('250');
    expect(demoWrapper.text()).not.toContain('Себест.');
  });

  it('preserves service tariff, estimate, and installation command emits', async () => {
    const wrapper = mount(OrderServiceLinesEditor, {
      props: baseProps([
        { service_id: null, title: 'Монтаж', quantity: 1, price: 500, cost: 100 },
      ], { compact: true, editingIndex: 0, showEstimateImport: true, selectedEstimateId: estimate.id, activeSuggestionIndex: 0 }),
      global: {
        stubs: {
          OrderServiceCatalogPicker: {
            template: `<div data-testid="catalog-stub">
              <button @click='$emit("choose", { tariff_id: 91, price: 600 })'>Выбрать тариф</button>
              <button @click='$emit("standard-installation", { id: 9 }, false)'>Стандартный монтаж</button>
              <button @click='$emit("open-installation-estimate")'>Открыть расчёт</button>
            </div>`,
            emits: ['choose', 'standard-installation', 'open-installation-estimate', 'close', 'custom', 'created-estimate'],
          },
        },
      },
    });
    mounted.push(wrapper);

    await wrapper.get('[data-testid="select-service-91"]').trigger('click');
    await wrapper.get('[data-testid="import-estimate"]').trigger('click');
    await wrapper.get('[data-testid="add-service-line"]').trigger('click');
    await wrapper.findAll('button').find((button) => button.text() === 'Выбрать тариф')!.trigger('click');
    await wrapper.get('[data-testid="add-service-line"]').trigger('click');
    await wrapper.findAll('button').find((button) => button.text() === 'Стандартный монтаж')!.trigger('click');
    await wrapper.get('[data-testid="add-service-line"]').trigger('click');
    await wrapper.findAll('button').find((button) => button.text() === 'Открыть расчёт')!.trigger('click');

    expect(wrapper.emitted('select')).toEqual([[{ index: 0, option: tariff }]]);
    expect(wrapper.emitted('importEstimate')).toEqual([[]]);
    expect(wrapper.emitted('addTariff')).toEqual([[{ tariff_id: 91, price: 600 }]]);
    expect(wrapper.emitted('standardInstallation')).toEqual([[{ id: 9 }, false]]);
    expect(wrapper.emitted('openInstallationEstimate')).toEqual([[]]);
  });
});
