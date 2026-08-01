import { effectScope, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderCommercialEditor } from '../src/composables/useOrderCommercialEditor';

const apiMock = vi.hoisted(() => ({
  smartSearchProducts: vi.fn(),
}));

vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/services/ui-feedback', () => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
}));

const order = ref({ id: 42 } as ManagerOrderDetailResponse);
let scope: EffectScope;

const createEditor = () => {
  scope = effectScope();
  return scope.run(() => useOrderCommercialEditor({
    order,
    setToast: vi.fn(),
    persistDraft: vi.fn(),
  }))!;
};

beforeEach(() => {
  apiMock.smartSearchProducts.mockResolvedValue([]);
});

afterEach(() => {
  scope?.stop();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('useOrderCommercialEditor', () => {
  it('owns line validation and normalizes the proposal command payload', () => {
    const editor = createEditor();
    editor.productLines.value = [{
      link_id: 5,
      product_id: 9,
      product_query: 'Gree Pular',
      quantity: 2,
      price: 1_500.4,
      cost: 1_000.4,
      logistics_components: [{
        title: 'Наружный блок',
        country: '',
        unit: '',
        quantity_per_parent: 0,
        unit_price: -5,
        kind: 'unknown' as any,
      }],
    }];
    editor.serviceLines.value = [{
      service_id: 7,
      title: 'Монтаж',
      quantity: 1,
      price: 500,
      cost: 200,
    }];

    expect(editor.validateLines()).toBe('');
    expect(editor.buildLinesPayload(17)).toEqual({
      products: [{
        product_id: 9,
        quantity: 2,
        price: 1_500,
        cost: 1_000,
        logistics_components: [{
          title: 'Наружный блок',
          country: 'Китай',
          unit: 'шт.',
          quantity_per_parent: 1,
          unit_price: 0,
          kind: 'other',
        }],
        link_id: 5,
        proposal_id: 17,
      }],
      services: [{
        service_id: 7,
        title: 'Монтаж',
        quantity: 1,
        price: 500,
        cost: 200,
        link_id: null,
        proposal_id: 17,
      }],
    });
  });

  it('keeps stock filtering and product lookup inside the commercial boundary', async () => {
    vi.useFakeTimers();
    apiMock.smartSearchProducts.mockResolvedValue([
      { id: 1, title: 'Есть на складе', vitebsk_qty: 1, minsk_qty: 0, availability_status: 'in_stock' },
      { id: 2, title: 'Нет на складе', vitebsk_qty: 0, minsk_qty: 0, availability_status: 'out_of_stock' },
    ]);
    const editor = createEditor();
    editor.productLines.value = [{
      link_id: null,
      product_id: 0,
      product_query: 'Gree',
      quantity: 1,
      price: 0,
      cost: 0,
    }];
    editor.searchInStock.value = true;
    editor.onProductQueryInput(0);
    await vi.advanceTimersByTimeAsync(450);

    expect(apiMock.smartSearchProducts).toHaveBeenCalledWith('Gree', 20);
    expect(editor.productOptions.value.map((item) => item.id)).toEqual([1]);
    expect(editor.productLookupById.value[1]?.title).toBe('Есть на складе');
  });
});
