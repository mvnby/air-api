import { effectScope, ref, type EffectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useOrderWorkspaceUsage } from '../src/composables/useOrderWorkspaceUsage';
import { CancelablePromise } from '../src/client/core/CancelablePromise';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

type DeferredRequest = Promise<unknown> & { cancel: ReturnType<typeof vi.fn> };
const deferredRequest = (): DeferredRequest => {
  const promise = new Promise<unknown>(() => undefined) as DeferredRequest;
  promise.cancel = vi.fn();
  return promise;
};

let scope: EffectScope;
const requests: DeferredRequest[] = [];
const record = vi.fn(() => {
  const request = deferredRequest();
  requests.push(request);
  return request;
});

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  requests.splice(0);
  managerSession.isAuthenticated.value = true;
  managerSession.auth.value = { tenant_id: 7, staff_user_id: 13, username: 'manager', capabilities: [] } as any;
  managerStorefrontSelection.selectedSlug.value = 'minsk';
  localStorage.clear();
});
afterEach(() => {
  scope?.stop();
  vi.useRealTimers();
  managerSession.isAuthenticated.value = false;
  managerSession.auth.value = null;
  managerStorefrontSelection.selectedSlug.value = null;
});

const createUsage = () => {
  const open = ref(false);
  const ready = ref(false);
  const orderKey = ref(42);
  const workflow = ref('repair');
  const customer = ref({ type: 'individual_entrepreneur' } as any);
  scope = effectScope();
  const usage = scope.run(() => useOrderWorkspaceUsage({ open, ready, orderKey, workflow, customer }, { record }))!;
  return { usage, open, ready, orderKey, workflow, customer };
};

describe('useOrderWorkspaceUsage', () => {
  it('does not count rehydration of the same open order as another opening', async () => {
    const state = createUsage();
    state.open.value = true;
    state.ready.value = true;
    state.ready.value = false;
    state.ready.value = true;
    await vi.advanceTimersByTimeAsync(2_000);
    expect(record.mock.calls[0]?.[0]).toHaveLength(1);
  });
  it('records only the finite event dimensions after the order form is ready', async () => {
    const state = createUsage();
    state.open.value = true;
    state.ready.value = true;
    await vi.advanceTimersByTimeAsync(2_000);

    expect(record).toHaveBeenCalledWith([{
      metric: 'order_open', workflow: 'repair', party_kind: 'individual_entrepreneur', viewport: 'desktop',
    }]);
  });

  it('does not buffer events when the account-scoped preference is disabled', async () => {
    const state = createUsage();
    state.usage.toggle();
    state.usage.track('product_add');
    await vi.advanceTimersByTimeAsync(2_000);

    expect(state.usage.enabled.value).toBe(false);
    expect(record).not.toHaveBeenCalled();
    expect(localStorage.getItem('manager:order-workspace-usage:v1:7:staff-13:minsk')).toBe('off');
  });

  it('rejects values outside the finite metric vocabulary', async () => {
    const state = createUsage();
    state.usage.track('free-form-input' as any);
    await vi.advanceTimersByTimeAsync(2_000);

    expect(record).not.toHaveBeenCalled();
  });

  it('cancels an in-flight batch and drops queued events before a storefront scope changes', async () => {
    const state = createUsage();
    state.usage.track('proposal_open');
    await vi.advanceTimersByTimeAsync(2_000);
    state.usage.track('product_add');

    managerStorefrontSelection.selectedSlug.value = 'vitebsk';

    expect(requests[0]?.cancel).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(2_000);
    expect(record).toHaveBeenCalledOnce();
  });

  it('flushes a bounded batch immediately at 25 events', () => {
    const state = createUsage();
    for (let index = 0; index < 25; index += 1) state.usage.track('service_add');

    expect(record).toHaveBeenCalledOnce();
    expect(record.mock.calls[0]?.[0]).toHaveLength(25);
  });

  it('continues with a later batch after a real CancelablePromise settles', async () => {
    const open = ref(false);
    const workflow = ref('maintenance');
    const customer = ref({ type: 'company' } as any);
    const orderKey = ref(101);
    const settledRecord = vi.fn(() => new CancelablePromise<unknown>((resolve) => resolve({ accepted: 1 })));
    scope = effectScope();
    const usage = scope.run(() => useOrderWorkspaceUsage({ open, orderKey, workflow, customer }, { record: settledRecord }))!;

    usage.track('proposal_open');
    await vi.advanceTimersByTimeAsync(2_000);
    await Promise.resolve();
    usage.track('documents_open');
    await vi.advanceTimersByTimeAsync(2_000);

    expect(settledRecord).toHaveBeenCalledTimes(2);
  });

  it('bounds queued events behind a stalled request and drops the uncertain batch after timeout', async () => {
    const state = createUsage();
    state.usage.track('proposal_open');
    await vi.advanceTimersByTimeAsync(2_000);
    for (let index = 0; index < 120; index += 1) state.usage.track('service_add');

    await vi.advanceTimersByTimeAsync(12_000);

    expect(requests[0]?.cancel).toHaveBeenCalledOnce();
    expect(record.mock.calls[1]?.[0]).toHaveLength(25);
  });

  it('records a fresh open after the drawer loads another order without leaking an identifier', async () => {
    const open = ref(false);
    const ready = ref(false);
    const orderKey = ref(42);
    const workflow = ref('repair');
    const customer = ref({ type: 'company' } as any);
    const settledRecord = vi.fn(() => new CancelablePromise<unknown>((resolve) => resolve({ accepted: 1 })));
    scope = effectScope();
    const usage = scope.run(() => useOrderWorkspaceUsage({ open, ready, orderKey, workflow, customer }, { record: settledRecord }))!;
    open.value = true;
    ready.value = true;
    await vi.advanceTimersByTimeAsync(2_000);
    await Promise.resolve();
    orderKey.value = 43;
    await vi.advanceTimersByTimeAsync(2_000);

    expect(settledRecord).toHaveBeenCalledTimes(2);
    expect(settledRecord.mock.calls.flat().flat()).not.toContain(42);
    expect(settledRecord.mock.calls.flat().flat()).not.toContain(43);
  });
});
