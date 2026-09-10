import { computed, effectScope, nextTick, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import type { ProductLine } from '../src/components/orders/order-editor-types';
import { useOrderDrawerSaving } from '../src/composables/useOrderDrawerSaving';

const ordersMock = vi.hoisted(() => ({ patchManagerOrder: vi.fn() }));
const preferenceMock = vi.hoisted(() => ({ current: null as any }));

vi.mock('../src/client', () => ({ ManagerOrdersService: ordersMock }));
vi.mock('../src/composables/useOrderAutosavePreference', () => ({
  useOrderAutosavePreference: () => preferenceMock.current,
}));

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
};

const deferred = <T,>(): Deferred<T> => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

const proposal = (id = 17) => ({
  id,
  name: 'Основной вариант',
  status: 'draft',
  is_selected: true,
  is_archived: false,
  sort_order: 0,
  total_amount: 0,
  total_cost: 0,
  margin: 0,
  product_lines: [],
  service_lines: [],
});

const orderResponse = (id = 42, proposalId = 17, title = '') => ({
  id,
  title,
  status: 'negotiation',
  is_paid: false,
  product_lines: [],
  service_lines: [],
  proposals: [proposal(proposalId)],
}) as ManagerOrderDetailResponse;

let scope: EffectScope;

const createSaving = () => {
  const order = ref<ManagerOrderDetailResponse | null>(orderResponse());
  const ready = ref(true);
  const activeProposalId = ref<number | null>(17);
  const activeProposalLocked = ref(false);
  const form = ref('исходный заголовок');
  const productLines = ref<ProductLine[]>([]);
  const serviceLines = ref<any[]>([]);
  const currentFormSnapshot = () => form.value;
  const currentLinesSnapshot = () => JSON.stringify({
    products: productLines.value,
    services: serviceLines.value,
  });
  const savedFormSnapshot = ref(currentFormSnapshot());
  const savedLinesSnapshot = ref(currentLinesSnapshot());
  const hasUnsavedChanges = computed(() => (
    currentFormSnapshot() !== savedFormSnapshot.value
    || currentLinesSnapshot() !== savedLinesSnapshot.value
  ));
  const buildSavePayload = vi.fn(() => ({
    title: form.value,
    products: productLines.value.map((line) => ({
      link_id: line.link_id ?? null,
      product_id: line.product_id,
      quantity: line.quantity,
      price: line.price,
      cost: line.cost,
    })),
    services: serviceLines.value.map((line) => ({ ...line })),
  }));
  const hydrateOrder = vi.fn((updated: ManagerOrderDetailResponse) => {
    form.value = updated.title || '';
  });
  const localFormError = ref('');
  const localServerErrors = ref<Record<string, string>>({});
  const clearDraft = vi.fn();
  const onUpdated = vi.fn();
  scope = effectScope();
  const saving = scope.run(() => useOrderDrawerSaving({
    order,
    ready,
    activeProposalId,
    activeProposalLocked,
    productLines,
    currentFormSnapshot,
    currentLinesSnapshot,
    savedFormSnapshot,
    savedLinesSnapshot,
    hasUnsavedChanges,
    buildSavePayload,
    hydrateOrder,
    localFormError,
    localServerErrors,
    clearDraft,
    onUpdated,
  }))!;
  saving.resetBaseline();
  return {
    activeProposalId,
    activeProposalLocked,
    buildSavePayload,
    clearDraft,
    form,
    hasUnsavedChanges,
    hydrateOrder,
    localFormError,
    onUpdated,
    order,
    productLines,
    ready,
    savedFormSnapshot,
    savedLinesSnapshot,
    saving,
    serviceLines,
  };
};

beforeEach(() => {
  preferenceMock.current = {
    enabled: ref(true),
    identity: ref('1:manager'),
    toggle: vi.fn(),
  };
  ordersMock.patchManagerOrder.mockReset();
  ordersMock.patchManagerOrder.mockResolvedValue(orderResponse());
});

afterEach(() => {
  scope?.stop();
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('useOrderDrawerSaving', () => {
  it('awaits an explicit flush before document generation and drawer close', async () => {
    const state = createSaving();
    const first = deferred<ManagerOrderDetailResponse>();
    state.form.value = 'правка перед документом';
    ordersMock.patchManagerOrder.mockReturnValueOnce(first.promise);

    const beforeDocument = state.saving.beforeDocumentGenerate();
    await Promise.resolve();
    await Promise.resolve();
    expect(ordersMock.patchManagerOrder).toHaveBeenCalledWith(42, { title: 'правка перед документом' });

    let documentFinished = false;
    void beforeDocument.then(() => { documentFinished = true; });
    await Promise.resolve();
    expect(documentFinished).toBe(false);
    first.resolve(orderResponse(42, 17, 'правка перед документом'));
    await expect(beforeDocument).resolves.toEqual({ mutated: true });

    const second = deferred<ManagerOrderDetailResponse>();
    state.form.value = 'правка перед закрытием';
    ordersMock.patchManagerOrder.mockReturnValueOnce(second.promise);
    const beforeClose = state.saving.beforeClose();
    await Promise.resolve();
    await Promise.resolve();
    expect(ordersMock.patchManagerOrder).toHaveBeenLastCalledWith(42, { title: 'правка перед закрытием' });

    second.resolve(orderResponse(42, 17, 'правка перед закрытием'));
    await expect(beforeClose).resolves.toBe(true);
  });

  it('does not write automatically in manual mode and blocks documents with dirty data', async () => {
    vi.useFakeTimers();
    preferenceMock.current.enabled.value = false;
    const state = createSaving();
    state.form.value = 'ручная правка';
    await nextTick();
    await vi.advanceTimersByTimeAsync(1_000);

    expect(ordersMock.patchManagerOrder).not.toHaveBeenCalled();
    await expect(state.saving.beforeDocumentGenerate()).resolves.toBe(false);
    expect(state.localFormError.value).toContain('Сохраните изменения');
  });

  it('ignores a late response after the order scope changes', async () => {
    const state = createSaving();
    const request = deferred<ManagerOrderDetailResponse>();
    state.form.value = 'правка старого заказа';
    ordersMock.patchManagerOrder.mockReturnValueOnce(request.promise);
    const save = state.saving.flush();
    await Promise.resolve();
    await Promise.resolve();

    state.order.value = orderResponse(99, 33, 'новый заказ');
    state.activeProposalId.value = 33;
    await nextTick();
    request.resolve(orderResponse(42, 17, 'устаревший ответ'));

    await expect(save).resolves.toBe(false);
    expect(state.hydrateOrder).not.toHaveBeenCalled();
    expect(state.onUpdated).not.toHaveBeenCalled();
    expect(state.savedFormSnapshot.value).toBe('исходный заголовок');
  });

  it('does not hydrate an old response over newer form input', async () => {
    const state = createSaving();
    const firstRequest = deferred<ManagerOrderDetailResponse>();
    const secondRequest = deferred<ManagerOrderDetailResponse>();
    state.form.value = 'первая правка';
    ordersMock.patchManagerOrder
      .mockReturnValueOnce(firstRequest.promise)
      .mockReturnValueOnce(secondRequest.promise);
    const save = state.saving.flush();
    await Promise.resolve();
    await Promise.resolve();

    state.form.value = 'новая правка';
    firstRequest.resolve(orderResponse(42, 17, 'ответ на первую правку'));
    await vi.waitFor(() => expect(ordersMock.patchManagerOrder).toHaveBeenCalledTimes(2));

    expect(state.hydrateOrder).not.toHaveBeenCalled();
    expect(state.form.value).toBe('новая правка');

    secondRequest.resolve(orderResponse(42, 17, 'новая правка'));
    await expect(save).resolves.toBe(true);
  });

  it('sends products and services in the active line scope and reconciles product link IDs', async () => {
    const state = createSaving();
    state.productLines.value = [{
      link_id: null,
      product_id: 9,
      product_query: 'Gree Pular',
      quantity: 2,
      price: 1_500,
      cost: 1_000,
    }];
    state.serviceLines.value = [{
      link_id: null,
      service_id: 7,
      title: 'Монтаж',
      quantity: 1,
      price: 500,
      cost: 200,
    }];
    ordersMock.patchManagerOrder.mockResolvedValueOnce({
      ...orderResponse(),
      proposals: [{
        ...proposal(),
        product_lines: [{ product_id: 9, id: 501 }],
      }],
    });

    await expect(state.saving.flush()).resolves.toBe(true);

    expect(ordersMock.patchManagerOrder).toHaveBeenCalledWith(42, {
      products: [{
        link_id: null,
        product_id: 9,
        quantity: 2,
        price: 1_500,
        cost: 1_000,
      }],
      services: [{
        link_id: null,
        service_id: 7,
        title: 'Монтаж',
        quantity: 1,
        price: 500,
        cost: 200,
      }],
      line_proposal_id: 17,
    });
    expect(state.productLines.value[0].link_id).toBe(501);
    expect(JSON.parse(state.savedLinesSnapshot.value).products[0].link_id).toBe(501);
  });
});
