import { effectScope } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useCatalogUsage } from '../src/composables/useCatalogUsage';
import { managerSession } from '../src/services/manager-session';

let scope: ReturnType<typeof effectScope>;
const record = vi.fn(() => Object.assign(Promise.resolve({ accepted: 1 }), { cancel: vi.fn() }));
const deferredRequest = () => Object.assign(new Promise<unknown>(() => undefined), { cancel: vi.fn() });

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  localStorage.clear();
  managerSession.isAuthenticated.value = true;
  managerSession.auth.value = { tenant_id: 1, staff_user_id: 8, username: 'pilot' } as any;
});
afterEach(() => {
  scope?.stop();
  vi.useRealTimers();
  managerSession.isAuthenticated.value = false;
  managerSession.auth.value = null;
});

describe('useCatalogUsage', () => {
  it('updates editors already mounted in the same account when the pilot is toggled', async () => {
    scope = effectScope();
    const [list, editor] = scope.run(() => [useCatalogUsage({ record }), useCatalogUsage({ record })])!;
    list!.setOptIn(true);
    editor!.track('edit_basics');
    await vi.advanceTimersByTimeAsync(2_000);
    expect(record).toHaveBeenCalledOnce();
    list!.setOptIn(false);
    expect(editor!.enabled.value).toBe(false);
    editor!.track('edit_basics');
    await vi.advanceTimersByTimeAsync(2_000);
    expect(record).toHaveBeenCalledOnce();
  });

  it('does not send any event before the account-local pilot opt-in', async () => {
    scope = effectScope();
    const usage = scope.run(() => useCatalogUsage({ record }))!;
    usage.track('product_open');
    await vi.advanceTimersByTimeAsync(2_000);
    expect(record).not.toHaveBeenCalled();
  });

  it('sends a bounded content-free batch after opt-in', async () => {
    scope = effectScope();
    const usage = scope.run(() => useCatalogUsage({ record }))!;
    usage.setOptIn(true);
    usage.track('media_load', 'success', 1_500);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(localStorage.getItem('manager:catalog-usage:v1:1:staff-8')).toBe('on');
    expect(record).toHaveBeenCalledWith([{
      device: 'desktop', action: 'media_load', outcome: 'success', duration_bucket: '1_3s',
    }]);
  });

  it('flushes an opted-in navigation event when the component scope is disposed', async () => {
    scope = effectScope();
    const usage = scope.run(() => useCatalogUsage({ record }))!;
    usage.setOptIn(true);
    usage.track('product_open');

    scope.stop();
    await Promise.resolve();

    expect(record).toHaveBeenCalledWith([{
      device: 'desktop', action: 'product_open', outcome: 'success', duration_bucket: 'none',
    }]);
  });

  it('cancels a stalled batch and continues with later buffered events', async () => {
    const stalled = deferredRequest();
    const transport = { record: vi.fn().mockReturnValueOnce(stalled).mockImplementation(() => record()) };
    scope = effectScope();
    const usage = scope.run(() => useCatalogUsage(transport))!;
    usage.setOptIn(true);
    usage.track('product_open');
    await vi.advanceTimersByTimeAsync(2_000);
    usage.track('media_load');

    await vi.advanceTimersByTimeAsync(10_000);
    expect(stalled.cancel).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(2_000);

    expect(transport.record).toHaveBeenNthCalledWith(2, [{
      device: 'desktop', action: 'media_load', outcome: 'success', duration_bucket: 'none',
    }]);
  });
});
