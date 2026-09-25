import { computed, onScopeDispose, ref, watch, type Ref } from 'vue';
import { ManagerOrdersService, type ManagerOrderDetailResponse } from '../client';
import type { ServiceLine } from '../components/orders/order-editor-types';
import { managerSession } from '../services/manager-session';

type Options = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  open: Readonly<Ref<boolean>>;
  proposalId: Readonly<Ref<number | null>>;
  serviceLines: Ref<ServiceLine[]>;
  dirty: Readonly<Ref<boolean>>;
  flush: () => Promise<boolean>;
  clearDraft: () => void;
  onUpdated: (order: ManagerOrderDetailResponse) => void;
};

/** Serializes attachment with order autosave and keeps replies inside their original scope. */
export const useOrderInstallationAttachment = (options: Options) => {
  const busy = ref(false);
  const autosavePaused = ref(false);
  const lockKey = ref<string | null>(null);
  const lockToken = ref<string | null>(null);
  const scopeKey = computed(() => {
    const auth = managerSession.auth.value;
    const identity = auth ? `${auth.tenant_id}:${auth.staff_user_id || auth.username}` : 'anonymous';
    return `manager.installation-order:${identity}:${options.order.value?.id}:${options.proposalId.value}`;
  });
  const end = (token: string) => {
    if (lockToken.value !== token) return;
    autosavePaused.value = false;
    busy.value = false;
    lockKey.value = null;
    lockToken.value = null;
  };
  watch(scopeKey, (currentKey) => {
    if (lockKey.value && lockKey.value !== currentKey && lockToken.value) end(lockToken.value);
  }, { flush: 'sync' });
  watch(options.open, (isOpen) => {
    if (!isOpen && lockToken.value) end(lockToken.value);
  }, { flush: 'sync' });
  onScopeDispose(() => { if (lockToken.value) end(lockToken.value); });

  const matches = (orderId: number, proposalId: number, key: string, token: string) => (
    options.open.value && options.order.value?.id === orderId && options.proposalId.value === proposalId
    && scopeKey.value === key && lockKey.value === key && lockToken.value === token
  );
  const begin = async (orderId: number, proposalId: number, key: string, token: string) => {
    if (busy.value || !options.open.value || options.order.value?.id !== orderId
      || options.proposalId.value !== proposalId || scopeKey.value !== key) return false;
    busy.value = true;
    lockKey.value = key;
    lockToken.value = token;
    let prepared = false;
    try {
      const saved = await options.flush();
      if (!matches(orderId, proposalId, key, token) || !saved) return false;
      autosavePaused.value = true;
      prepared = true;
      return true;
    } finally {
      if (!prepared) end(token);
    }
  };
  const after = async (orderId: number, proposalId: number, key: string, token: string): Promise<boolean> => {
    if (!matches(orderId, proposalId, key, token)) return false;
    const fresh = await ManagerOrdersService.getManagerOrderDetail(orderId);
    if (!matches(orderId, proposalId, key, token)) return false;
    if (options.dirty.value) {
      const proposal = (fresh.proposals || []).find((item) => item.id === proposalId);
      if (!proposal) throw new Error('Предложение изменилось. Обновите заказ.');
      const known = new Set(options.serviceLines.value.map((line) => line.link_id));
      const attached = (proposal.service_lines || []).filter((line) => (
        line.installation_estimate_revision_id && !known.has(line.id)
      ));
      options.serviceLines.value.push(...attached.map((line) => ({
        link_id: line.id, installation_estimate_revision_id: line.installation_estimate_revision_id,
        installation_projection_mode: line.installation_projection_mode,
        service_id: line.service_id, title: line.service_title,
        quantity: line.quantity, price: Number(line.price), cost: Number(line.cost || 0),
      })));
      autosavePaused.value = false;
      if (!await options.flush()) throw new Error('Монтаж прикреплён, но новые правки не сохранились. Повторите прикрепление, чтобы обновить карточку.');
      if (!matches(orderId, proposalId, key, token)) return false;
      const saved = await ManagerOrdersService.getManagerOrderDetail(orderId);
      if (!matches(orderId, proposalId, key, token)) return false;
      options.clearDraft();
      options.onUpdated(saved);
      return true;
    }
    options.clearDraft();
    options.onUpdated(fresh);
    return true;
  };
  return { busy, autosavePaused, begin, after, end };
};
