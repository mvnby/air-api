import { effectScope, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderCommercialEditor } from '../src/composables/useOrderCommercialEditor';
import { buildKnownProductClientDescription } from '../src/components/orders/product-client-description';

const apiMock = vi.hoisted(() => ({
  smartSearchProducts: vi.fn(),
}));
const feedbackMock = vi.hoisted(() => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
}));

vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/services/ui-feedback', () => ({
  confirmDialog: feedbackMock.confirmDialog,
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
      client_description: 'Инвертор; цвет: серебристый',
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
        client_description: 'Инвертор; цвет: серебристый',
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

  it('fills only catalog-backed metrics and preserves manual text without confirmation', async () => {
    const catalogProduct = {
      id: 9,
      title: 'Gree Pular',
      price: 3_000,
      cost: 2_000,
      is_inverter: true,
      power_cooling: null,
      availability_status: 'in_stock',
      vitebsk_qty: 1,
      minsk_qty: 0,
      specs: {
        area_m2: '35',
        capacity_cooling_kw: '3.2',
        color: 'Серебристый',
      },
    };
    expect(buildKnownProductClientDescription(catalogProduct)).toBe(
      'Инвертор; площадь: 35 м²; охлаждение: 3,2 кВт; цвет: Серебристый',
    );
    expect(buildKnownProductClientDescription({
      ...catalogProduct,
      is_inverter: false,
      power_cooling: null,
      specs: { inverter: false },
    })).toBe('');
    expect(buildKnownProductClientDescription({
      ...catalogProduct,
      is_inverter: true,
      specs: { compressor_type_norm: 'on_off', inverter: false },
    })).toBe('Инвертор');
    expect(buildKnownProductClientDescription({
      ...catalogProduct,
      is_inverter: false,
      specs: { compressor_type_norm: 'on_off', indoor_type: 'настенный' },
    })).toBe('On/Off; тип внутреннего блока: настенный');

    const editor = createEditor();
    editor.productLines.value = [{
      link_id: 5,
      product_id: 9,
      product_query: 'Gree Pular',
      client_description: 'Ручное уточнение',
      quantity: 1,
      price: 3_000,
      cost: 2_000,
    }];
    editor.productLookupById.value = { 9: catalogProduct };
    feedbackMock.confirmDialog.mockResolvedValueOnce(false);

    await editor.fillProductClientDescription(0);

    expect(feedbackMock.confirmDialog).toHaveBeenCalled();
    expect(editor.productLines.value[0]?.client_description).toBe('Ручное уточнение');
    expect(editor.productLines.value[0]?.product_id).toBe(9);
    expect(editor.productLines.value[0]?.product_query).toBe('Gree Pular');
  });

  it('autofills a newly selected catalog product but keeps hydration exact', () => {
    const editor = createEditor();
    editor.loadLines([{
      id: 5,
      proposal_id: 17,
      product_id: 9,
      product_title: 'Gree Pular',
      client_description: 'Сохранённый текст',
      quantity: 1,
      price: 3_000,
      cost: 2_000,
      is_installation_included: false,
      installation_price: 0,
      line_total: 3_000,
      product_logistics_components: [],
      logistics_components: [],
    } as any], []);
    expect(editor.productLines.value[0]?.client_description).toBe('Сохранённый текст');

    editor.selectProductForLine(0, {
      id: 10,
      title: 'MDV Aurora',
      price: 3_200,
      is_inverter: true,
      power_cooling: 2.6,
      availability_status: 'in_stock',
      vitebsk_qty: 1,
      minsk_qty: 0,
      specs: { color: 'Белый' },
    });
    expect(editor.productLines.value[0]?.client_description).toBe(
      'Инвертор; охлаждение: 2,6 кВт; цвет: Белый',
    );
  });

  it('ignores a late catalog response after the manager changes the product', async () => {
    let resolveSearch!: (value: unknown[]) => void;
    apiMock.smartSearchProducts.mockReturnValueOnce(new Promise((resolve) => {
      resolveSearch = resolve;
    }));
    const editor = createEditor();
    editor.productLines.value = [{
      link_id: 5,
      product_id: 9,
      product_query: 'Gree Pular',
      client_description: 'Ручное описание',
      quantity: 1,
      price: 3_000,
      cost: 2_000,
    }];

    const filling = editor.fillProductClientDescription(0);
    editor.productLines.value[0]!.product_id = 10;
    editor.productLines.value[0]!.product_query = 'MDV Aurora';
    resolveSearch([{
      id: 9,
      title: 'Gree Pular',
      is_inverter: true,
      specs: { area_m2: 35 },
    }]);
    await filling;

    expect(editor.productLines.value[0]?.client_description).toBe('Ручное описание');
    expect(feedbackMock.confirmDialog).not.toHaveBeenCalled();
    expect(editor.productLookupById.value[9]).toBeUndefined();
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
