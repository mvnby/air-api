import { computed, ref, type Ref } from 'vue';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../manager-capabilities';
import { managerSession } from '../services/manager-session';
import { catalogDecisionUrl, navigateManager } from '../services/catalog-decision-context';

export const useOrderCatalogNavigation = (options: {
  orderId: Readonly<Ref<number | undefined>>;
  proposalId: Readonly<Ref<number | null>>;
  status: Readonly<Ref<string>>;
  locked: Readonly<Ref<boolean>>;
  busy: Readonly<Ref<boolean>>;
  flush: () => Promise<boolean>;
  close: () => void;
}) => {
  const opening = ref(false);
  const available = computed(() => Boolean(options.orderId.value && options.proposalId.value
    && options.status.value === 'negotiation' && !options.locked.value
    && hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.platformManage)));
  const open = async () => {
    if (!available.value || options.busy.value || opening.value) return;
    const orderId = options.orderId.value!;
    const proposalId = options.proposalId.value!;
    const returnTo = `${window.location.pathname}${window.location.search}`;
    opening.value = true;
    try {
      if (!await options.flush()) return;
      if (!available.value || orderId !== options.orderId.value || proposalId !== options.proposalId.value) return;
      options.close();
      navigateManager(catalogDecisionUrl(orderId, proposalId, returnTo));
    } finally { opening.value = false; }
  };
  return { available, opening, open };
};
