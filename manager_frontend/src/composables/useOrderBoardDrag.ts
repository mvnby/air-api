import { computed, inject, onMounted, onScopeDispose, ref, watch, type InjectionKey } from 'vue';
import type { ManagerOrderListItemResponse } from '../client';
import { getOrderBoardColumn } from '../components/orders/order-utils';

type Source = { orderId: number; oldStatus: string };
type Options = {
  context: () => string; disabled: () => boolean; pending: () => number[];
  find: (id: number) => ManagerOrderListItemResponse | undefined;
  phases: () => Record<string, string>;
};
export const useOrderBoardDrag = (options: Options) => {
  const source = ref<Source | null>(null), hover = ref<string | null>(null);
  const depths = new Map<string, number>();
  let leaveFrame: number | null = null;
  const stopLeave = () => { if (leaveFrame !== null) cancelAnimationFrame(leaveFrame); leaveFrame = null; };
  const cancel = () => { stopLeave(); source.value = null; hover.value = null; depths.clear(); };
  const available = computed(() => {
    const order = source.value && options.find(source.value.orderId);
    return Boolean(order && !options.disabled() && !options.pending().includes(order.id) && ['negotiation', 'execution'].includes(order.status) && getOrderBoardColumn(order) === source.value?.oldStatus);
  });
  const allowed = (target: string) => available.value && ['negotiation', 'execution', 'closed_lost', 'closed_won'].includes(target)
    && target !== source.value?.oldStatus;
  const start = (payload: Source) => {
    cancel();
    const order = options.find(payload.orderId);
    if (!order || options.disabled() || options.pending().includes(order.id) || !['negotiation', 'execution'].includes(order.status)) return;
    source.value = { orderId: order.id, oldStatus: getOrderBoardColumn(order) };
  };
  const over = (event: DragEvent, target: string) => {
    if (!allowed(target)) { stopLeave(); hover.value = null; depths.clear(); if (event.dataTransfer) event.dataTransfer.dropEffect = 'none'; return; }
    event.preventDefault(); stopLeave(); hover.value = target;
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
  };
  const enter = (event: DragEvent, target: string) => {
    if (!allowed(target)) return;
    depths.set(target, (depths.get(target) || 0) + 1); over(event, target);
  };
  const leave = (event: DragEvent, target: string) => {
    depths.set(target, Math.max(0, (depths.get(target) || 0) - 1));
    const root = event.currentTarget as HTMLElement;
    if (event.relatedTarget instanceof Node) {
      if (root.contains(event.relatedTarget)) return;
      depths.delete(target);
    } else if (depths.get(target)) return;
    stopLeave();
    leaveFrame = requestAnimationFrame(() => { leaveFrame = null; if (hover.value === target && !depths.get(target)) hover.value = null; });
  };
  const drop = (target: string) => {
    const payload = allowed(target) && source.value ? { ...source.value, newStatus:
      target === 'negotiation' && options.phases()[target] ? options.phases()[target]!
        : target === 'execution' && options.phases()[target] ? `execution:${options.phases()[target]}` : target } : null;
    cancel(); return payload;
  };
  watch(options.context, cancel, { flush: 'sync' });
  watch(available, value => { if (!value && source.value) cancel(); }, { flush: 'sync' });
  const escape = (event: KeyboardEvent) => { if (event.key === 'Escape') cancel(); };
  onMounted(() => { document.addEventListener('keydown', escape, true); document.addEventListener('dragend', cancel, true); document.addEventListener('drop', cancel); window.addEventListener('blur', cancel); });
  onScopeDispose(() => { cancel(); document.removeEventListener('keydown', escape, true); document.removeEventListener('dragend', cancel, true); document.removeEventListener('drop', cancel); window.removeEventListener('blur', cancel); }, true);
  return { source, hover, available, allowed, start, enter, over, leave, drop, cancel };
};
export type OrderBoardDrag = ReturnType<typeof useOrderBoardDrag>;
export const orderBoardDragKey: InjectionKey<OrderBoardDrag> = Symbol('order-board-drag');
export const useSharedOrderBoardDrag = () => inject(orderBoardDragKey, null);
