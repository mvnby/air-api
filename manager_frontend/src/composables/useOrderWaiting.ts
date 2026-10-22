import { computed, nextTick, onScopeDispose, ref, watch } from 'vue';
import type { ManagerOrderListItemResponse, ManagerOrderDetailResponse, ManagerOrderWaitingCommand } from '../client';
import { api } from '../api';
import { orderWaitingApi } from '../services/order-waiting';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { getApiErrorMessage } from '../utils/api-errors';

type Options = {
  current?: () => ManagerOrderListItemResponse | null | undefined;
  beforeAction?: () => Promise<boolean>;
  updated: (order: ManagerOrderDetailResponse) => void | Promise<void>;
  notify: (message: string) => void;
};
export const useOrderWaiting = (options: Options) => {
  const selected = ref<ManagerOrderListItemResponse | null>(null);
  const busy = ref(false), busyOrderId = ref<number | null>(null), error = ref(''), stale = ref(false);
  const identity = computed(() => `${managerSession.auth.value?.username}:${managerSession.auth.value?.tenant_id}:${managerStorefrontSelection.selectedSlug.value}`);
  let generation = 0;
  const close = () => { if (!busy.value) { selected.value = null; error.value = ''; stale.value = false; } };
  const invalidate = () => { generation++; selected.value = null; busy.value = false; busyOrderId.value = null; error.value = ''; stale.value = false; };
  watch(identity, invalidate, { flush: 'sync' });
  onScopeDispose(invalidate, true);
  const execute = async (order: ManagerOrderListItemResponse, payload: ManagerOrderWaitingCommand) => {
    const version = generation;
    busy.value = true; busyOrderId.value = order.id; error.value = '';
    try {
      const result = await orderWaitingApi.command(order.id, payload);
      if (version !== generation) return;
      selected.value = null;
      await options.updated(result);
      options.notify(payload.action === 'wait' ? 'Заказ в ожидании' : 'Заказ возвращён в работу');
    } catch (cause) {
      if (version !== generation) return;
      error.value = getApiErrorMessage(cause);
      stale.value = (cause as { status?: number }).status === 409;
      if (!selected.value) options.notify(error.value);
    } finally { if (version === generation) { busy.value = false; busyOrderId.value = null; } }
  };
  const toggle = async (provided?: ManagerOrderListItemResponse) => {
    if (busy.value || managerSession.auth.value?.demo_read_only) return;
    const version = generation;
    busy.value = true;
    try {
      if (options.beforeAction && !await options.beforeAction()) return;
      await nextTick();
      if (version !== generation) return;
      const order = options.current?.() || provided;
      if (!order || !['negotiation', 'execution'].includes(order.status)) return;
      if (order.is_on_hold) await execute(order, { action: 'resume', expected_revision: order.workflow_revision || 0 });
      else { selected.value = { ...order }; error.value = ''; stale.value = false; }
    } finally { if (version === generation) busy.value = false; }
  };
  const submit = async (form: Omit<ManagerOrderWaitingCommand, 'action' | 'expected_revision'>) => {
    if (!selected.value || busy.value || stale.value) return;
    await execute(selected.value, { ...form, action: 'wait', expected_revision: selected.value.workflow_revision || 0 });
  };
  const refresh = async () => {
    if (!selected.value || busy.value) return;
    const orderId = selected.value.id, version = generation;
    busy.value = true;
    try {
      const current = await api.getManagerOrderDetail(orderId);
      if (version !== generation) return;
      selected.value = current; // The dialog watches ID only and retains all entered text/date.
      stale.value = !['negotiation', 'execution'].includes(current.status);
      error.value = stale.value ? 'Заказ уже закрыт. Ожидание недоступно.' : '';
    } catch (cause) { if (version === generation) error.value = getApiErrorMessage(cause); }
    finally { if (version === generation) busy.value = false; }
  };
  return { selected, busy, busyOrderId, error, stale, toggle, submit, refresh, close };
};
