import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import OrderServiceLinesEditor from '../src/components/orders/OrderServiceLinesEditor.vue';
import ServiceDescriptionModeSwitch from '../src/components/orders/ServiceDescriptionModeSwitch.vue';
import type { ServiceLine } from '../src/components/orders/order-editor-types';
import { managerSession } from '../src/services/manager-session';

const apiMock = vi.hoisted(() => ({ listManagerQuickTariffs: vi.fn() }));
vi.mock('../src/api', () => ({ api: apiMock }));

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

apiMock.listManagerQuickTariffs.mockImplementation(async () => ({ items: [tariff] }));

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
  it('renders accepted calculations as grouped rows with direct edit and remove actions', async () => {
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
    expect(wrapper.text()).toContain('По расчёту');
    expect(wrapper.findAll('[data-order-usage="order_service_edit"]')).toHaveLength(2);
    expect(wrapper.findAll('[data-order-usage="order_service_remove"]')).toHaveLength(2);
    await wrapper.get('[data-testid="compact-service-row-0-1"] [data-order-usage="order_service_edit"]').trigger('click');
    await wrapper.get('[data-testid="compact-service-row-0-0"] [data-order-usage="order_service_remove"]').trigger('click');
    expect(wrapper.emitted('editInstallation')).toEqual([[0, 1]]);
    expect(wrapper.emitted('remove')).toEqual([[0, 0]]);
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

    expect(wrapper.findAll('textarea')).toHaveLength(2);
    expect(wrapper.findAll('button[data-order-usage="order_service_edit"]')).toHaveLength(1);
    expect(wrapper.get('button[data-order-usage="order_service_edit"]').attributes('aria-label')).toContain('#1');
    await wrapper.getComponent(ServiceDescriptionModeSwitch).get('button[aria-pressed="false"]').trigger('click');
    expect(wrapper.emitted('descriptionMode')).toEqual([[{ index: 1, mode: 'full' }]]);
    expect(wrapper.emitted('remove')).toBeUndefined();
    await wrapper.get('[data-testid="service-client-description"]').setValue('Монтаж лесов; трасса до 5 метров');
    expect(lines[1]!.description).toBe('Монтаж лесов; трасса до 5 метров');
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

  it('selects a suggestion in the title field and preserves estimate import as an optional action', async () => {
    const wrapper = mountEditor([
      { service_id: null, title: 'Монтаж', quantity: 1, price: 500, cost: 100 },
    ], { compact: true, editingIndex: 0, showEstimateImport: true, selectedEstimateId: estimate.id });
    await wrapper.get('[data-testid="service-title-input"]').trigger('focus');
    await flushPromises();
    await wrapper.get('[data-testid="select-service-91"]').trigger('click');
    await wrapper.get('[data-testid="import-estimate"]').trigger('click');
    await wrapper.get('[data-testid="add-service-line"]').trigger('click');
    expect(wrapper.emitted('select')).toEqual([[{ index: 0, option: tariff, quantity: undefined }]]);
    expect(wrapper.emitted('importEstimate')).toEqual([[]]);
    expect(wrapper.emitted('add')).toEqual([[]]);
    expect(wrapper.find('[data-testid="service-catalog-picker"]').exists()).toBe(false);
  });
});
