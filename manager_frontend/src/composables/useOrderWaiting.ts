import { computed, nextTick, onScopeDispose, ref, watch } from 'vue';
import type { ManagerOrderListItemResponse, ManagerOrderDetailResponse, ManagerOrderWaitingCommand } from '../client';
import { api } from '../api';
import { orderWaitingApi } from '../services/order-waiting';
import { managerSession } from '../services/manager-session';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { getApiErrorMessage } from '../utils/api-errors';
import { useOrderCommandOwnership, type OrderCommandOwnership, type OrderCommandToken } from './useOrderCommandOwnership';

type Options = {
  current?: () => ManagerOrderListItemResponse | null | undefined;
  beforeAction?: () => Promise<boolean>;
  context?: () => string;
  ownership?: OrderCommandOwnership;
  actionable?: () => boolean;
  updated: (order: ManagerOrderDetailResponse) => void | boolean | Promise<void | boolean>;
  notify: (message: string) => void;
};
export const useOrderWaiting = (options: Options) => {
  const selected = ref<ManagerOrderListItemResponse | null>(null);
  const error = ref(''), stale = ref(false);
  const identity = computed(() => `${managerSession.auth.value?.staff_user_id || managerSession.auth.value?.username}:${managerSession.auth.value?.tenant_id}:${managerStorefrontSelection.selectedSlug.value}`);
  const scope = computed(() => `${identity.value}:${options.current?.()?.id ?? ''}:${options.context?.() ?? ''}`);
  const ownership = options.ownership || useOrderCommandOwnership(() => scope.value, {
    identity: () => identity.value,
    revalidate: async token => {
      if (!options.current || options.current()?.id !== token.orderId || options.actionable?.() === false) return;
      const version = scope.value;
      const result = await api.getManagerOrderDetail(token.orderId);
      if (scope.value === version) await options.updated(result);
    },
  });
  let generation = 0;
  const busy = computed(() => ownership.pendingIds.value.includes(selected.value?.id ?? options.current?.()?.id ?? -1));
  const busyOrderId = computed(() => ownership.pendingIds.value[0] ?? null);
  const invalidate = () => { generation++; selected.value = null; error.value = ''; stale.value = false; };
  watch(scope, invalidate, { flush: 'sync' });
  onScopeDispose(invalidate, true);
  const close = () => { if (!busy.value) { selected.value = null; error.value = ''; stale.value = false; } };
  const allowed = () => !managerSession.auth.value?.demo_read_only && (options.actionable?.() ?? true);
  const start = (id: number) => {
    if (!allowed()) return null;
    const token = ownership.begin(id);
    if (!token) options.notify(`Заказ №${id} уже сохраняется`);
    return token;
  };
  const execute = async (token: OrderCommandToken, payload: ManagerOrderWaitingCommand) => {
    const version = generation;
    const current = () => version === generation && ownership.current(token);
    error.value = '';
    try {
      let result: ManagerOrderDetailResponse;
      try { result = await ownership.write(token, () => orderWaitingApi.command(token.orderId, payload)); }
      catch (cause) {
        if (!current()) return;
        const message = getApiErrorMessage(cause);
        if (selected.value?.id === token.orderId) { error.value = message; stale.value = (cause as { status?: number }).status === 409; }
        else options.notify(message);
        return;
      }
      if (!current()) return;
      if (selected.value?.id === token.orderId) selected.value = null;
      let refreshed: void | boolean = false;
      try { refreshed = await options.updated(result); } catch { /* The write succeeded; a later read is a separate outcome. */ }
      if (!current()) return;
      const message = payload.action === 'wait' ? 'Заказ в ожидании' : 'Заказ возвращён в работу';
      options.notify(refreshed === false ? `${message}. Не удалось обновить данные — повторите загрузку.` : message);
    } finally { ownership.finish(token); }
  };
  const toggle = async (provided?: ManagerOrderListItemResponse) => {
    const initial = options.current?.() || provided;
    if (!initial) return;
    if (selected.value && selected.value.id !== initial.id) { options.notify('Завершите или закройте открытый диалог ожидания'); return; }
    const token = start(initial.id); if (!token) return;
    const version = generation;
    try {
      if (options.beforeAction && !await options.beforeAction()) return;
      await nextTick();
      if (version !== generation || !ownership.current(token) || !allowed()) return;
      const order = options.current?.() || provided;
      if (!order || order.id !== initial.id || !['negotiation', 'execution'].includes(order.status)) return;
      if (order.is_on_hold) await execute(token, { action: 'resume', expected_revision: order.workflow_revision || 0 });
      else { selected.value = { ...order }; error.value = ''; stale.value = false; }
    } finally { ownership.finish(token); }
  };
  const submit = async (form: Omit<ManagerOrderWaitingCommand, 'action' | 'expected_revision'>) => {
    if (!selected.value || stale.value) return;
    const token = start(selected.value.id); if (!token) return;
    await execute(token, { ...form, action: 'wait', expected_revision: selected.value.workflow_revision || 0 });
  };
  const refresh = async () => {
    if (!selected.value) return;
    const token = start(selected.value.id); if (!token) return;
    const version = generation;
    try {
      const current = await api.getManagerOrderDetail(token.orderId);
      if (version !== generation || !ownership.current(token)) return;
      selected.value = current; // The dialog watches ID only and retains all entered text/date.
      stale.value = !['negotiation', 'execution'].includes(current.status);
      error.value = stale.value ? 'Заказ уже закрыт. Ожидание недоступно.' : '';
    } catch (cause) { if (version === generation && ownership.current(token)) error.value = getApiErrorMessage(cause); }
    finally { ownership.finish(token); }
  };
  return { selected, busy, busyOrderId, error, stale, toggle, submit, refresh, close };
};
