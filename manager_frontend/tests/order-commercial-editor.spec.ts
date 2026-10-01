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
  const legacyInstallation = () => ({ id: 10, service_id: null, service_title: 'Установка №1…№5',
    quantity: 1, price: 3300, cost: 0, line_total: 3300, installation_estimate_revision_id: 5,
    installation_projection_mode: 'collapsed', installation_display_lines: [
      { title: 'Монтаж настенного кондиционера', quantity: 5, price: 600, description: 'Трасса 3 м' },
      { title: 'Сборка лесов', quantity: 2, price: 150, description: 'По согласованию' },
    ] });

  it('edits a legacy display group as a manual commercial row without changing the accepted source', () => {
    const editor = createEditor();
    const response = legacyInstallation();
    editor.loadLines([], [response]);
    editor.editInstallationLine(0, 1);
    expect(editor.editingServiceLineIndex.value).toBe(1);
    expect(editor.total.value).toBe(3300);
    expect(editor.serviceLines.value.every((line) => !line.link_id && !line.installation_estimate_revision_id)).toBe(true);
    const line = editor.serviceLines.value[1]!;
    line.title = 'Монтаж лесов';
    line.description = 'Согласованная формулировка';
    line.price = 125.55;
    const payload = editor.buildLinesPayload(17).services;
    expect(payload[1]).toMatchObject({ title: 'Монтаж лесов', description: 'Согласованная формулировка', quantity: 2, price: 125.55 });
    expect(payload[0]).toMatchObject({ title: 'Монтаж настенного кондиционера', description: 'Трасса 3 м', quantity: 5, price: 600 });
    expect(response.installation_display_lines[1]).toMatchObject({ title: 'Сборка лесов', price: 150 });
  });

  it('deletes only the selected legacy group and leaves the other work in the same proposal', async () => {
    const editor = createEditor();
    editor.loadLines([], [legacyInstallation()]);
    await editor.removeServiceLine(0, 0);
    expect(editor.serviceLines.value).toHaveLength(1);
    expect(editor.buildLinesPayload(17).services[0]).toMatchObject({ link_id: null, title: 'Сборка лесов', quantity: 2, price: 150 });
    expect(editor.total.value).toBe(300);
  });

  it('retains frozen provenance if deletion is cancelled', async () => {
    const editor = createEditor();
    editor.loadLines([], [legacyInstallation()]);
    const original = editor.currentLinesSnapshot(17);
    feedbackMock.confirmDialog.mockResolvedValueOnce(false);
    await editor.removeServiceLine(0, 1);
    expect(editor.currentLinesSnapshot(17)).toBe(original);
    expect(editor.serviceLines.value[0]!.installation_estimate_revision_id).toBe(5);
  });

  it('removes all commercial bindings of the edited revision while keeping other calculations', () => {
    const editor = createEditor();
    const first = legacyInstallation();
    const sibling = { id: 11, service_id: null, service_title: 'Подключение', quantity: 1, price: 100, line_total: 100,
      description: 'Старое согласованное описание', installation_estimate_revision_id: 5 };
    const other = { id: 12, service_id: null, service_title: 'Другая смета', quantity: 1, price: 700, line_total: 700,
      installation_estimate_revision_id: 6 };
    editor.loadLines([], [first, sibling, other]);
    editor.editInstallationLine(1);
    expect(editor.editingServiceLineIndex.value).toBe(2);
    expect(editor.serviceLines.value[2]).toMatchObject({ title: 'Подключение', description: 'Старое согласованное описание', price: 100 });
    expect(editor.serviceLines.value[2]!.installation_estimate_revision_id).toBeUndefined();
    expect(editor.serviceLines.value[3]!.installation_estimate_revision_id).toBe(6);
    expect(editor.total.value).toBe(4100);
  });

  it('includes manual description changes in autosave and preserves explicit clearing through reload', () => {
    const editor = createEditor();
    editor.serviceLines.value = [{ link_id: 10, title: 'Монтаж', description: 'До 3 метров', quantity: 5, price: 600, cost: 0 }];
    const original = editor.currentLinesSnapshot(17);
    editor.serviceLines.value[0]!.description = 'До 5 метров';
    expect(editor.currentLinesSnapshot(17)).not.toBe(original);
    expect(editor.buildLinesPayload(17).services[0]!.description).toBe('До 5 метров');
    editor.serviceLines.value[0]!.description = '';
    expect(editor.buildLinesPayload(17).services[0]!.description).toBeNull();
    editor.loadLines([], [{ id: 10, service_title: 'Монтаж лесов', description: 'До 5 метров', quantity: 5, price: 550, line_total: 2750 }]);
    expect(editor.buildLinesPayload(17).services[0]).toMatchObject({ title: 'Монтаж лесов', description: 'До 5 метров', price: 550 });
  });

  it('uses canonical catalog price for loaded discounted products and marks unknown fallbacks', () => {
    const editor = createEditor();
    editor.loadLines([
      { id: 1, product_id: 2, product_title: 'MDV', price: 2480, catalog_price: 2690, quantity: 5, line_total: 12400, is_installation_included: false, installation_price: 0 },
      { id: 2, product_id: 3, product_title: 'Без цены', price: 2000, quantity: 1, line_total: 2000, is_installation_included: false, installation_price: 0 },
    ], []);
    editor.syncProductLookupFromLines();
    expect(editor.productLookupById.value[2]).toMatchObject({ price: 2690, catalog_price_known: true });
    expect(editor.productLookupById.value[3]).toMatchObject({ price: 2000, catalog_price_known: false });
    expect(editor.buildLinesPayload(17).products[0]!.price).toBe(2480);
    expect(editor.buildLinesPayload(17).products[0]).not.toHaveProperty('catalog_price');
  });
  it('keeps legacy frozen row bytes in save payload while showing grouped presentation', () => {
    const editor = createEditor();
    editor.loadLines([], [{ id: 10, service_id: null, service_title: 'Установка №1…№5',
      quantity: 1, price: 3000, line_total: 3000, installation_estimate_revision_id: 5,
      installation_projection_mode: 'collapsed', installation_display_lines: [{
        title: 'Монтаж настенного кондиционера', quantity: 5, price: 600, description: 'Трасса 3 м',
      }] }]);
    expect(editor.serviceLines.value[0]?.installation_display_lines?.[0]?.quantity).toBe(5);
    expect(editor.buildLinesPayload(17).services).toEqual([{ link_id: 10, service_id: null,
      title: 'Установка №1…№5', quantity: 1, price: 3000, cost: 0, proposal_id: 17 }]);
  });
  it('preserves cents from estimate import through save and reload', () => {
    const editor = createEditor();
    editor.appendEstimateLines([
      { service_id: null, title: 'Работа 1', quantity: 1, price: 100.4, cost: 0 },
      { service_id: null, title: 'Работа 2', quantity: 1, price: 100.4, cost: 0 },
    ]);
    expect(editor.total.value).toBe(200.8);
    expect(editor.buildLinesPayload(17).services.map((line) => line.price)).toEqual([100.4, 100.4]);

    editor.loadLines([], [
      { id: 1, proposal_id: 17, service_id: null, service_title: 'Работа 1', quantity: 1, price: 100.4, cost: 0, line_total: 100.4 },
      { id: 2, proposal_id: 17, service_id: null, service_title: 'Работа 2', quantity: 1, price: 100.4, cost: 0, line_total: 100.4 },
    ] as any);
    expect(editor.buildLinesPayload(17).services.map((line) => line.price)).toEqual([100.4, 100.4]);
    expect(editor.validateLines()).toBe('');
  });

  it('saves cleared service cost as absent while keeping zero explicit', () => {
    const editor = createEditor();
    editor.serviceLines.value = [{ service_id: 7, title: 'Монтаж', quantity: 1, price: 100.4, cost: 50 }];

    for (const clearedCost of ['', null, undefined]) {
      editor.serviceLines.value[0]!.cost = clearedCost as any; // v-model.number emits '' when cleared.
      expect(editor.validateLines()).toBe('');
      expect(editor.buildLinesPayload(17).services[0]?.cost).toBeNull();
    }

    editor.serviceLines.value[0]!.cost = 0;
    expect(editor.validateLines()).toBe('');
    expect(editor.buildLinesPayload(17).services[0]?.cost).toBe(0);
  });

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
