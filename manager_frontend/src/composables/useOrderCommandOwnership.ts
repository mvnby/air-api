import { computed, onScopeDispose, ref, watch } from 'vue';

export type OrderCommandToken = Readonly<{
  orderId: number; sequence: number; context: string; identity: string; generation: number;
}>;
type Options = {
  identity: () => string;
  revalidate: (token: OrderCommandToken) => void | Promise<unknown>;
};
export const useOrderCommandOwnership = (context: () => string, options: Options) => {
  const owners = ref<Record<string, OrderCommandToken>>({});
  const writes = new Set<number>();
  let sequence = 0, generation = 0, active = true;
  const key = (identity: string, orderId: number) => JSON.stringify([identity, orderId]);
  const sameIdentity = (token: OrderCommandToken) => active && options.identity() === token.identity;
  const current = (token: OrderCommandToken) => sameIdentity(token) && generation === token.generation
    && context() === token.context && owners.value[key(token.identity, token.orderId)]?.sequence === token.sequence;
  watch(context, () => {
    generation++;
    // Closing a dialog cancels its reservation. A sent write still owns the order
    // until the request settles and the current identity has revalidated its view.
    owners.value = Object.fromEntries(Object.entries(owners.value).filter(([, token]) => writes.has(token.sequence)));
  }, { flush: 'sync' });
  onScopeDispose(() => { active = false; owners.value = {}; }, true);
  const begin = (orderId: number) => {
    const identity = options.identity(), id = key(identity, orderId);
    if (!active || owners.value[id]) return null;
    const token = { orderId, sequence: ++sequence, context: context(), identity, generation };
    owners.value = { ...owners.value, [id]: token };
    return token;
  };
  const finish = (token: OrderCommandToken) => {
    const id = key(token.identity, token.orderId);
    if (writes.has(token.sequence) || owners.value[id]?.sequence !== token.sequence) return;
    const next = { ...owners.value }; delete next[id]; owners.value = next;
  };
  const write = async <T>(token: OrderCommandToken, persist: () => Promise<T>): Promise<T> => {
    if (!current(token) || writes.has(token.sequence)) throw new Error('Команда заказа уже недоступна');
    writes.add(token.sequence);
    try { return await persist(); }
    finally {
      try {
        if (sameIdentity(token) && !current(token)) await options.revalidate(token);
      } catch { /* Revalidation reports read errors separately from the settled write. */ }
      finally {
        writes.delete(token.sequence);
        if (!current(token)) finish(token);
      }
    }
  };
  return { begin, current, finish, write, context: computed(context),
    pendingIds: computed(() => Object.values(owners.value).filter(token => token.identity === options.identity()).map(token => token.orderId)),
  };
};
export type OrderCommandOwnership = ReturnType<typeof useOrderCommandOwnership>;
