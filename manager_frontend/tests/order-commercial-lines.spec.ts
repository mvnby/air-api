import { mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrderProductLinesEditor from '../src/components/orders/OrderProductLinesEditor.vue';
import OrderServiceLinesEditor from '../src/components/orders/OrderServiceLinesEditor.vue';
import type {
  ProductLine,
  ProductOption,
  ServiceLine,
} from '../src/components/orders/order-editor-types';
import { managerSession } from '../src/services/manager-session';

const productLine: ProductLine = {
  link_id: 301,
  product_id: 0,
  product_query: 'Gr',
  quantity: 1,
  price: 1_500,
  cost: 1_000,
};
const productOption: ProductOption = {
  id: 501,
  title: 'Gree Pular',
  price: 1_700,
  cost: 1_100,
  is_inverter: true,
  power_cooling: 2.5,
  availability_status: 'in_stock',
  vitebsk_qty: 2,
  minsk_qty: 1,
};
const serviceLine: ServiceLine = {
  service_id: null,
  title: 'Монтаж',
  quantity: 1,
  price: 500,
  cost: 200,
};
const serviceOption = {
  tariff_id: 91,
  service_kind: 'installation' as const,
  short_name: 'Стандартный монтаж',
  full_description: 'Стандартный монтаж кондиционера с трассой до 3 метров',
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

const mountedWrappers: VueWrapper[] = [];

beforeEach(() => {
  managerSession.auth.value = { capabilities: ['platform.manage'] } as any;
});

afterEach(() => {
  for (const wrapper of mountedWrappers.splice(0)) wrapper.unmount();
  managerSession.auth.value = null;
});

describe('OrderProductLinesEditor', () => {
  it('renders catalog guidance and delegates product and supply commands', async () => {
    const supplyBadgeForLine = vi.fn(() => ({
      label: 'бронь',
      requestId: 1,
      status: 'reserved',
    }));
    const wrapper = mount(OrderProductLinesEditor, {
      props: {
        lines: [
          { ...productLine },
          {
            ...productLine,
            link_id: 302,
            product_id: productOption.id,
            product_query: productOption.title,
          },
        ],
        searchInStock: false,
        productOptions: [productOption],
        productLookupById: { [productOption.id]: productOption },
        productLookupLoading: false,
        activeSuggestionIndex: 0,
        supplyActionLoadingLineId: null,
        supplyBadgeForLine,
      },
    });
    mountedWrappers.push(wrapper);

    expect(wrapper.text()).toContain('Gree Pular');
    expect(wrapper.text()).toContain('Поставка: бронь');
    await wrapper.get(`[data-testid="select-product-${productOption.id}"]`).trigger('click');
    const reserveButtons = wrapper.findAll('button').filter((button) => (
      button.text().includes('Забронировать')
    ));
    await reserveButtons[1]?.trigger('click');
    await wrapper.get('[data-testid="add-product-line"]').trigger('click');

    expect(wrapper.emitted('select')).toEqual([[{ index: 0, option: productOption }]]);
    expect(wrapper.emitted('supply')).toEqual([[{
      line: expect.objectContaining({ link_id: 302 }),
      intent: 'reserve',
    }]]);
    expect(wrapper.emitted('add')).toEqual([[]]);
  });

  it('hides stock, product workspace and supply controls from tenant managers', () => {
    managerSession.auth.value = {
      capabilities: ['crm.manage', 'catalog.master.read', 'storefront.offers.read'],
    } as any;
    const wrapper = mount(OrderProductLinesEditor, {
      props: {
        lines: [{ ...productLine, product_id: productOption.id }],
        searchInStock: false,
        productOptions: [productOption],
        productLookupById: { [productOption.id]: productOption },
        productLookupLoading: false,
        activeSuggestionIndex: null,
        supplyActionLoadingLineId: null,
        supplyBadgeForLine: () => null,
      },
    });
    mountedWrappers.push(wrapper);

    expect(wrapper.text()).not.toContain('В наличии');
    expect(wrapper.text()).not.toContain('Открыть ↗');
    expect(wrapper.text()).not.toContain('В поставку');
    expect(wrapper.text()).not.toContain('Забронировать');
  });
});

describe('OrderServiceLinesEditor', () => {
  it('delegates tariff selection and estimate import while keeping draft models controlled', async () => {
    const wrapper = mount(OrderServiceLinesEditor, {
      props: {
        lines: [{ ...serviceLine }],
        editingIndex: 0,
        showEstimateImport: true,
        selectedEstimateId: estimate.id,
        estimateSearchQuery: '',
        estimateImportMode: 'detailed',
        descriptionMode: 'short',
        serviceOptions: [serviceOption],
        serviceLookupLoading: false,
        activeSuggestionIndex: 0,
        estimateOptions: [estimate],
        estimateOptionsLoading: false,
        importingEstimate: false,
        formatServiceKind: () => 'монтаж',
      },
    });
    mountedWrappers.push(wrapper);

    await wrapper.get(`[data-testid="select-service-${serviceOption.tariff_id}"]`).trigger('click');
    await wrapper.get('[data-testid="import-estimate"]').trigger('click');
    await wrapper.get('[data-testid="add-service-line"]').trigger('click');

    expect(wrapper.emitted('select')).toEqual([[{ index: 0, option: serviceOption }]]);
    expect(wrapper.emitted('importEstimate')).toEqual([[]]);
    expect(wrapper.emitted('add')).toEqual([[]]);
  });
});
