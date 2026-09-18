import { computed, onScopeDispose, ref, watch } from 'vue';
import {
  CATALOG_USAGE_ACTIONS,
  CATALOG_USAGE_OUTCOMES,
  type CatalogUsageAction,
  type CatalogUsageDurationBucket,
  type CatalogUsageEvent,
  type CatalogUsageOutcome,
  catalogUsageApi,
} from '../services/catalog-usage-api';
import { managerSession } from '../services/manager-session';

type CancelableRequest<T> = Promise<T> & { cancel: () => void };
type UsageTransport = { record: (events: CatalogUsageEvent[]) => CancelableRequest<unknown> };

const BATCH_DELAY_MS = 2_000;
const REQUEST_TIMEOUT_MS = 10_000;
const MAX_BATCH_SIZE = 25;
const MAX_BUFFERED_EVENTS = 100;
const STORAGE_KEY_PREFIX = 'manager:catalog-usage:v1';
// Same-tab editors are mounted before the pilot switch is changed.
const preferenceChange = ref<{ scope: string; enabled: boolean } | null>(null);

const storage = () => {
  try { return typeof window === 'undefined' ? null : window.localStorage; } catch { return null; }
};
const device = (): CatalogUsageEvent['device'] => {
  const width = typeof window === 'undefined' ? 0 : window.innerWidth;
  if (width < 640) return 'mobile';
  if (width < 1024) return 'tablet';
  return 'desktop';
};
const isAction = (value: string): value is CatalogUsageAction => (CATALOG_USAGE_ACTIONS as readonly string[]).includes(value);
const isOutcome = (value: string): value is CatalogUsageOutcome => (CATALOG_USAGE_OUTCOMES as readonly string[]).includes(value);
const durationBucket = (durationMs: number | undefined): CatalogUsageDurationBucket => {
  if (!Number.isFinite(durationMs)) return 'none';
  if (durationMs! < 1_000) return 'under_1s';
  if (durationMs! < 3_000) return '1_3s';
  if (durationMs! < 10_000) return '3_10s';
  if (durationMs! < 30_000) return '10_30s';
  return 'over_30s';
};

export const useCatalogUsage = (transport: UsageTransport = catalogUsageApi) => {
  const enabled = ref(false);
  const bufferedEvents = ref<CatalogUsageEvent[]>([]);
  let pendingRequest: CancelableRequest<unknown> | null = null;
  let flushTimer: ReturnType<typeof window.setTimeout> | null = null;
  let requestTimeout: ReturnType<typeof window.setTimeout> | null = null;
  let disposed = false;

  const scope = computed(() => {
    const auth = managerSession.auth.value;
    if (!managerSession.isAuthenticated.value || !auth) return '';
    const account = auth.staff_user_id ? `staff-${auth.staff_user_id}` : `user-${auth.username}`;
    return `${auth.tenant_id}:${account}`;
  });
  const storageKey = computed(() => scope.value ? `${STORAGE_KEY_PREFIX}:${scope.value}` : '');
  const clearTimer = () => {
    if (flushTimer !== null) window.clearTimeout(flushTimer);
    flushTimer = null;
  };
  const clearBufferedState = () => {
    clearTimer();
    clearRequestTimeout();
    bufferedEvents.value = [];
    pendingRequest?.cancel();
    pendingRequest = null;
  };
  const clearRequestTimeout = () => {
    if (requestTimeout !== null) window.clearTimeout(requestTimeout);
    requestTimeout = null;
  };
  const loadPreference = () => {
    try { enabled.value = Boolean(storageKey.value && storage()?.getItem(storageKey.value) === 'on'); } catch { enabled.value = false; }
  };
  const scheduleFlush = () => {
    if (disposed || flushTimer !== null || pendingRequest || !bufferedEvents.value.length) return;
    flushTimer = window.setTimeout(flush, BATCH_DELAY_MS);
  };
  const flush = () => {
    clearTimer();
    if (!enabled.value || !scope.value || pendingRequest || !bufferedEvents.value.length) return;
    const events = bufferedEvents.value.splice(0, MAX_BATCH_SIZE);
    const requestScope = scope.value;
    const pending = transport.record(events);
    pendingRequest = pending;
    requestTimeout = window.setTimeout(() => {
      if (pendingRequest !== pending) return;
      pending.cancel();
      pendingRequest = null;
      requestTimeout = null;
      // The dispatched batch may have reached the API, so it cannot be retried safely.
      scheduleFlush();
    }, REQUEST_TIMEOUT_MS);
    void pending.catch(() => undefined).finally(() => {
      if (pendingRequest !== pending) return;
      clearRequestTimeout();
      pendingRequest = null;
      if (!disposed && enabled.value && scope.value === requestScope && bufferedEvents.value.length) scheduleFlush();
    });
  };
  const setOptIn = (value: boolean) => {
    enabled.value = value;
    try { if (storageKey.value) storage()?.setItem(storageKey.value, value ? 'on' : 'off'); } catch { /* keep current-session preference */ }
    preferenceChange.value = { scope: scope.value, enabled: value };
    if (!value) clearBufferedState();
  };
  const track = (action: CatalogUsageAction, outcome: CatalogUsageOutcome = 'success', durationMs?: number) => {
    if (!enabled.value || !scope.value || !isAction(action) || !isOutcome(outcome) || bufferedEvents.value.length >= MAX_BUFFERED_EVENTS) return;
    bufferedEvents.value.push({ device: device(), action, outcome, duration_bucket: durationBucket(durationMs) });
    if (bufferedEvents.value.length >= MAX_BATCH_SIZE) flush();
    else scheduleFlush();
  };

  watch(scope, () => { clearBufferedState(); loadPreference(); }, { immediate: true, flush: 'sync' });
  watch(preferenceChange, change => {
    if (!change || change.scope !== scope.value) return;
    enabled.value = change.enabled;
    if (!change.enabled) clearBufferedState();
  }, { flush: 'sync' });
  onScopeDispose(() => {
    clearTimer();
    flush();
    disposed = true;
    clearRequestTimeout();
  });
  return { enabled, setOptIn, track, flush };
};
