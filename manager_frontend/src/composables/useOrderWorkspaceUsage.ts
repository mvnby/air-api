import { computed, onScopeDispose, ref, watch, type Ref } from 'vue';
import type { OrderCustomerBrief } from '../client';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../manager-capabilities';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import {
  ORDER_WORKSPACE_USAGE_METRICS,
  type OrderWorkspaceUsageEvent,
  type OrderWorkspaceUsageMetric,
  type OrderWorkspaceUsageParty,
  type OrderWorkspaceUsageViewport,
  type OrderWorkspaceUsageWorkflow,
  orderWorkspaceUsageApi,
} from '../services/order-workspace-usage-api';

type CancelableRequest<T> = Promise<T> & { cancel: () => void };
type UsageTransport = {
  record: (events: OrderWorkspaceUsageEvent[]) => CancelableRequest<unknown>;
};

type UseOrderWorkspaceUsageOptions = {
  open: Readonly<Ref<boolean>>;
  ready?: Readonly<Ref<boolean>>;
  orderKey?: Readonly<Ref<number | string | null | undefined>>;
  workflow: Readonly<Ref<string>>;
  customer: Readonly<Ref<OrderCustomerBrief | null | undefined>>;
};

const BATCH_DELAY_MS = 2_000;
const MAX_BATCH_SIZE = 25;
const MAX_BUFFERED_EVENTS = 100;
const REQUEST_TIMEOUT_MS = 10_000;
const STORAGE_KEY_PREFIX = 'manager:order-workspace-usage:v1';

const storage = () => {
  try { return typeof window === 'undefined' ? null : window.localStorage; } catch { return null; }
};

const normalizeWorkflow = (value: string): OrderWorkspaceUsageWorkflow | null => (
  ['sales_installation', 'work', 'maintenance', 'repair'] as const
).includes(value as OrderWorkspaceUsageWorkflow) ? value as OrderWorkspaceUsageWorkflow : null;

const partyKind = (customer: OrderCustomerBrief | null | undefined): OrderWorkspaceUsageParty => {
  const type = String(customer?.type || '');
  if (type === 'company' || type === 'individual' || type === 'individual_entrepreneur') return type;
  return 'unknown';
};

const viewport = (): OrderWorkspaceUsageViewport => {
  const width = typeof window === 'undefined' ? 0 : window.innerWidth;
  if (width < 640) return 'mobile';
  if (width < 1024) return 'tablet';
  return 'desktop';
};
const isUsageMetric = (value: string): value is OrderWorkspaceUsageMetric => (
  (ORDER_WORKSPACE_USAGE_METRICS as readonly string[]).includes(value)
);

export const useOrderWorkspaceUsage = (
  options: UseOrderWorkspaceUsageOptions,
  transport: UsageTransport = orderWorkspaceUsageApi,
) => {
  const enabled = ref(true);
  const bufferedEvents = ref<OrderWorkspaceUsageEvent[]>([]);
  let pendingRequest: CancelableRequest<unknown> | null = null;
  let flushTimer: ReturnType<typeof window.setTimeout> | null = null;
  let requestTimeout: ReturnType<typeof window.setTimeout> | null = null;
  let trackedOpenIdentity = '';

  const scope = computed(() => {
    const auth = managerSession.auth.value;
    const slug = managerStorefrontSelection.selectedSlug.value;
    if (!managerSession.isAuthenticated.value || !auth || !slug) return '';
    const account = auth.staff_user_id ? `staff-${auth.staff_user_id}` : `user-${auth.username}`;
    return `${auth.tenant_id}:${account}:${slug}`;
  });
  const storageKey = computed(() => scope.value ? `${STORAGE_KEY_PREFIX}:${scope.value}` : '');
  const canViewReport = computed(() => hasManagerCapability(
    managerSession.auth.value,
    MANAGER_CAPABILITY.analyticsManage,
  ));

  const clearTimer = () => {
    if (flushTimer !== null) window.clearTimeout(flushTimer);
    flushTimer = null;
  };
  const clearRequestTimeout = () => {
    if (requestTimeout !== null) window.clearTimeout(requestTimeout);
    requestTimeout = null;
  };
  const clearBufferedState = () => {
    clearTimer();
    clearRequestTimeout();
    bufferedEvents.value = [];
    pendingRequest?.cancel();
    pendingRequest = null;
    trackedOpenIdentity = '';
  };

  const loadPreference = () => {
    try { enabled.value = !storageKey.value || storage()?.getItem(storageKey.value) !== 'off'; } catch { enabled.value = true; }
  };

  const flush = () => {
    clearTimer();
    if (!scope.value || !managerSession.isAuthenticated.value || pendingRequest || !bufferedEvents.value.length) return;
    const events = bufferedEvents.value.splice(0, MAX_BATCH_SIZE);
    const requestScope = scope.value;
    const pending = transport.record(events);
    pendingRequest = pending;
    requestTimeout = window.setTimeout(() => {
      if (pendingRequest !== pending) return;
      pending.cancel();
      pendingRequest = null;
      requestTimeout = null;
      // The dispatched batch is intentionally not restored: its outcome is uncertain.
      scheduleFlush();
    }, REQUEST_TIMEOUT_MS);
    void pending.catch(() => undefined).finally(() => {
      if (pendingRequest !== pending) return;
      clearRequestTimeout();
      pendingRequest = null;
      if (scope.value === requestScope && bufferedEvents.value.length) scheduleFlush();
    });
  };
  const scheduleFlush = () => {
    if (flushTimer !== null || pendingRequest || !bufferedEvents.value.length) return;
    flushTimer = window.setTimeout(flush, BATCH_DELAY_MS);
  };

  const track = (metric: OrderWorkspaceUsageMetric) => {
    const workflow = normalizeWorkflow(options.workflow.value);
    if (!isUsageMetric(metric) || !enabled.value || !scope.value || !managerSession.isAuthenticated.value || !workflow) return;
    if (bufferedEvents.value.length >= MAX_BUFFERED_EVENTS) return;
    bufferedEvents.value.push({ metric, workflow, party_kind: partyKind(options.customer.value), viewport: viewport() });
    if (bufferedEvents.value.length >= MAX_BATCH_SIZE) flush();
    else scheduleFlush();
  };

  const toggle = () => {
    enabled.value = !enabled.value;
    try {
      if (storageKey.value) storage()?.setItem(storageKey.value, enabled.value ? 'on' : 'off');
    } catch { /* The in-memory preference remains active for this drawer. */ }
    if (!enabled.value) clearBufferedState();
  };

  watch(scope, () => {
    clearBufferedState();
    loadPreference();
  }, { immediate: true, flush: 'sync' });

  watch([options.open, () => options.ready?.value ?? true, () => options.orderKey?.value ?? null, scope], ([open, ready, orderKey, currentScope]) => {
    const identity = open && ready && currentScope && orderKey !== null && orderKey !== undefined
      ? `${currentScope}:${orderKey}`
      : '';
    if (!open) trackedOpenIdentity = '';
    if (!identity) return;
    if (trackedOpenIdentity !== identity) {
      trackedOpenIdentity = identity;
      track('order_open');
    }
  }, { immediate: true, flush: 'sync' });

  onScopeDispose(clearBufferedState);

  return { canViewReport, enabled, flush, track, toggle };
};
