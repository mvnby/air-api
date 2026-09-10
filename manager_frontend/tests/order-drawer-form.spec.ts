import { effectScope, nextTick, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import { useOrderDrawerForm } from '../src/composables/useOrderDrawerForm';

const apiMock = vi.hoisted(() => ({
  getManagerInstallers: vi.fn(),
  listManagerQuickTariffs: vi.fn(),
}));
const settingsMock = vi.hoisted(() => ({ getFxRate: vi.fn() }));

vi.mock('../src/api', () => ({ api: apiMock }));
vi.mock('../src/client', () => ({ ManagerSettingsService: settingsMock }));
vi.mock('../src/services/ui-feedback', () => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
}));

let scope: EffectScope;

const order = {
  id: 42,
  status: 'negotiation',
  title: 'Монтаж в офисе',
  workflow_type: 'sales_installation',
  created_at: '2026-07-31T10:00:00Z',
  total_amount: 3_500,
  total_cost: 2_000,
  margin: 1_500,
  is_paid: false,
  manager_labels: ['важный'],
  comment: 'Позвонить заранее',
  delivery_address: 'Минск, ул. Ленина, 1',
  negotiation_status: 'awaiting_offer',
  product_lines: [],
  service_lines: [],
  payments: [],
  needs_attention: false,
  awaiting_measurement: false,
  client_thinking: false,
  ready_for_execution: false,
} as ManagerOrderDetailResponse;

const createForm = (validationError = '') => {
  const productLines = ref([{
    link_id: null,
    product_id: 9,
    product_query: 'Gree Pular',
    quantity: 1,
    price: 3_000,
    cost: 2_000,
  }]);
  const serviceLines = ref([{
    service_id: 7,
    title: 'Монтаж',
    quantity: 1,
    price: 500,
    cost: 0,
  }]);
  scope = effectScope();
  const buildLinesPayload = vi.fn().mockReturnValue({ products: [{ product_id: 9 }], services: [{ service_id: 7 }] });
  const form = scope.run(() => useOrderDrawerForm({
    total: ref(3_500),
    productLines,
    serviceLines,
    serviceTariffOptions: ref([]),
    activeServiceSuggestionIndex: ref(null),
    applyTariffTemplateToLine: vi.fn(),
    buildLinesPayload,
    validateLines: vi.fn().mockReturnValue(validationError),
    setToast: vi.fn(),
  }))!;
  return { form, buildLinesPayload };
};

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

beforeEach(() => {
  apiMock.getManagerInstallers.mockResolvedValue({ items: [] });
  apiMock.listManagerQuickTariffs.mockResolvedValue({ items: [] });
  settingsMock.getFxRate.mockResolvedValue({ usd_byn: 3.2, eur_byn: null });
});

afterEach(() => {
  scope?.stop();
  vi.clearAllMocks();
});

describe('useOrderDrawerForm', () => {
  it('hydrates the editable fields and builds the unchanged manager order contract', () => {
    const { form, buildLinesPayload } = createForm();
    form.hydrateOrder(order);

    const payload = form.buildSavePayload(false);

    expect(form.orderTitle.value).toBe('Монтаж в офисе');
    expect(form.customerDeliveryAddress.value).toBe('Минск, ул. Ленина, 1');
    expect(buildLinesPayload).toHaveBeenCalledOnce();
    expect(payload).toEqual(expect.objectContaining({
      status: 'negotiation',
      title: 'Монтаж в офисе',
      manager_labels: ['важный'],
      customer_delivery_address: 'Минск, ул. Ленина, 1',
      products: [{ product_id: 9 }],
      services: [{ service_id: 7 }],
    }));
  });

  it('keeps commercial validation errors out of the save command', () => {
    const { form, buildLinesPayload } = createForm('Выберите товар из выпадающего списка');
    form.hydrateOrder(order);

    expect(form.buildSavePayload(false)).toBeNull();
    expect(form.localServerErrors.value.products).toBe('Выберите товар из выпадающего списка');
    expect(form.localFormError.value).toBe('Исправьте ошибки в форме');
    expect(buildLinesPayload).not.toHaveBeenCalled();
  });

  it('treats an individual entrepreneur as B2B in the order form', () => {
    const { form } = createForm();
    const currentOrder = ref({
      ...order,
      customer: { type: 'individual_entrepreneur', inn: '' },
    });

    expect(form.isB2cCustomer(currentOrder).value).toBe(false);
  });

  it('keeps a saved EUR amount when the late FX lookup has no EUR rate', async () => {
    const { form } = createForm();
    form.hydrateOrder({
      ...order,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    });

    await nextTick();
    await Promise.resolve();

    expect(form.targetCurrency.value).toBe('EUR');
    expect(form.targetCurrencyAmount.value).toBe(1_250.75);
    expect(form.enableCurrency.value).toBe(true);
  });

  it('still blocks changed currency fields when the selected rate is unavailable', () => {
    const { form } = createForm();
    form.hydrateOrder({
      ...order,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    });
    form.targetCurrencyAmount.value = 1_300;

    expect(form.buildSavePayload(false, false, true)).toBeNull();
    expect(form.localFormError.value).toBe('Для выбранной валюты сейчас нет доступного курса');
  });

  it('does not recalculate a saved EUR amount from a cached rate during hydration', async () => {
    const { form } = createForm();
    form.currentFxRate.value = { usd_byn: 3.2, eur_byn: 3.5 };
    form.hydrateOrder({
      ...order,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    });

    await nextTick();

    expect(form.targetCurrency.value).toBe('EUR');
    expect(form.targetCurrencyAmount.value).toBe(1_250.75);
  });

  it('calculates the amount after a manager explicitly enables currency mode', async () => {
    const { form } = createForm();
    form.hydrateOrder(order);
    await nextTick();

    form.enableCurrency.value = true;
    await nextTick();
    await Promise.resolve();

    expect(form.targetCurrency.value).toBe('USD');
    expect(form.targetCurrencyAmount.value).toBe(1_093.75);
  });

  it('ignores an old FX response after hydrating another EUR order', async () => {
    const oldFxRate = deferred<{ usd_byn: number; eur_byn: number | null }>();
    settingsMock.getFxRate.mockReset();
    settingsMock.getFxRate.mockReturnValueOnce(oldFxRate.promise);
    const { form } = createForm();

    form.hydrateOrder({
      ...order,
      id: 42,
      target_currency: 'EUR',
      target_currency_amount: 1_250.75,
    });
    form.currentFxRate.value = { usd_byn: 3.2, eur_byn: 3.5 };
    form.hydrateOrder({
      ...order,
      id: 43,
      target_currency: 'EUR',
      target_currency_amount: 880.5,
    });

    oldFxRate.resolve({ usd_byn: 3.2, eur_byn: null });
    await Promise.resolve();
    await nextTick();

    expect(form.currentFxRate.value).toEqual({ usd_byn: 3.2, eur_byn: 3.5 });
    expect(form.targetCurrency.value).toBe('EUR');
    expect(form.targetCurrencyAmount.value).toBe(880.5);
  });
});
