import { ref, nextTick, type Ref } from 'vue';
import { ManagerOrdersService, type ManagerOrderDetailResponse } from '../client';

type Options = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  open: Readonly<Ref<boolean>>;
  proposalId: Readonly<Ref<number | null>>;
  otherCommandBusy: Readonly<Ref<boolean>>;
  flush: () => Promise<boolean>;
  clearDraft: () => void;
  onUpdated: (order: ManagerOrderDetailResponse) => void;
};

/** Serialize source mutations with autosave and hydrate before editing resumes. */
export const useOrderSourceCommand = (options: Options) => {
  const busy = ref(false);
  let preparing = false;
  let target: { orderId: number; proposalId: number | null } | null = null;
  const matches = (value: NonNullable<typeof target>) => (
    options.open.value && options.order.value?.id === value.orderId
    && options.proposalId.value === value.proposalId
  );
  const before = async () => {
    const orderId = options.order.value?.id;
    if (!orderId || busy.value || preparing || options.otherCommandBusy.value) return false;
    const requested = { orderId, proposalId: options.proposalId.value };
    preparing = true;
    try {
      if (!await options.flush() || !matches(requested) || options.otherCommandBusy.value) return false;
      target = requested;
      busy.value = true;
      return true;
    } finally { preparing = false; }
  };
  const after = async () => {
    const requested = target;
    if (!requested || !matches(requested)) return false;
    const fresh = await ManagerOrdersService.getManagerOrderDetail(requested.orderId);
    if (!matches(requested)) return false;
    options.clearDraft();
    options.onUpdated(fresh);
    await nextTick();
    return true;
  };
  const end = () => { busy.value = false; target = null; };
  return { busy, before, after, end };
};
