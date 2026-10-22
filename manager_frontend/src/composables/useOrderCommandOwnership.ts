import { computed, onScopeDispose, ref, watch } from 'vue';

export type OrderCommandToken = Readonly<{ orderId: number; sequence: number; context: string }>;
export const useOrderCommandOwnership = (context: () => string) => {
  const owners = ref<Record<number, OrderCommandToken>>({});
  let sequence = 0, active = true;
  const invalidate = () => { owners.value = {}; };
  watch(context, invalidate, { flush: 'sync' });
  onScopeDispose(() => { active = false; invalidate(); }, true);
  const current = (token: OrderCommandToken) => active && context() === token.context
    && owners.value[token.orderId]?.sequence === token.sequence;
  const begin = (orderId: number) => {
    if (!active || owners.value[orderId]) return null;
    const token = { orderId, sequence: ++sequence, context: context() };
    owners.value = { ...owners.value, [orderId]: token };
    return token;
  };
  const finish = (token: OrderCommandToken) => {
    if (!current(token)) return;
    const next = { ...owners.value }; delete next[token.orderId]; owners.value = next;
  };
  return { begin, current, finish, context: computed(context), pendingIds: computed(() => Object.keys(owners.value).map(Number)) };
};
export type OrderCommandOwnership = ReturnType<typeof useOrderCommandOwnership>;
