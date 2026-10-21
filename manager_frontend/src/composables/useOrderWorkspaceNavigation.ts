import { nextTick, ref, type Ref } from 'vue';
import type { OrderDrawerSectionsState } from './useOrderDrawerPersistence';
import type { OrderWorkflowType, OrderWorkspaceTarget } from '../components/orders/order-workspace';
import type { OrderWorkspaceSection } from '../components/orders/OrderWorkspaceNav.vue';
import { readOrderPage, readOrderWorkspaceSection } from '../services/order-navigation';
import { replaceManagerLocation } from '../services/manager-navigation-history';

type EquipmentPanelHandle = { collapse: () => void; expand: () => Promise<void> | void };
type DocumentsWorkspaceHandle = { openNative: () => void };

type UseOrderWorkspaceNavigationOptions = {
  status: Readonly<Ref<string>>;
  syncLocation?: Readonly<Ref<boolean>>;
  orderId?: Readonly<Ref<number | null | undefined>>;
  ensureSection?: (section: OrderWorkspaceSection) => Promise<void>;
  workflowType: Readonly<Ref<OrderWorkflowType>>;
  expandedSections: Ref<OrderDrawerSectionsState>;
  equipmentPanelRef: Ref<EquipmentPanelHandle | null>;
  documentsWorkspaceRef: Ref<DocumentsWorkspaceHandle | null>;
};

export const useOrderWorkspaceNavigation = ({
  status,
  syncLocation,
  orderId,
  ensureSection,
  workflowType,
  expandedSections,
  equipmentPanelRef,
  documentsWorkspaceRef,
}: UseOrderWorkspaceNavigationOptions) => {
  const executionWorkspaceOpen = ref(false);
  const activeWorkspaceTarget = ref<OrderWorkspaceTarget | null>(null);
  const locationMatches = () => Boolean(syncLocation?.value && orderId?.value && readOrderPage(window.location.href)?.orderId === orderId.value);
  const locationSection = () => locationMatches() ? readOrderWorkspaceSection(window.location.href) : 'proposal';
  const activeWorkspaceSection = ref<OrderWorkspaceSection>(locationSection());

  const sectionForTarget = (target: OrderWorkspaceTarget): OrderWorkspaceSection => {
    if (target === 'proposal') return 'proposal';
    if (target === 'documents') return 'documents';
    if (target === 'payments') return 'payments';
    return 'work';
  };

  const selectWorkspaceSection = (section: OrderWorkspaceSection, sync = true) => {
    activeWorkspaceSection.value = section;
    if (sync && locationMatches()) {
      const url = new URL(window.location.href);
      url.searchParams.set('section', section);
      replaceManagerLocation(`${url.pathname}${url.search}`);
    }
    if (section === 'proposal') expandedSections.value.proposals = true;
    if (section === 'documents') expandedSections.value.documents = true;
    if (section === 'payments') {
      if (status.value === 'execution') executionWorkspaceOpen.value = true;
      else expandedSections.value.payments = true;
    }
  };

  const resetWorkspaceNavigation = () => {
    executionWorkspaceOpen.value = false;
    activeWorkspaceTarget.value = null;
    selectWorkspaceSection(locationSection(), false);
  };

  const openWorkspaceTarget = async (target: OrderWorkspaceTarget, allowToggle = false) => {
    const shouldClose = allowToggle && activeWorkspaceTarget.value === target;
    if (activeWorkspaceTarget.value === 'equipment') equipmentPanelRef.value?.collapse();
    if (shouldClose) {
      activeWorkspaceTarget.value = null;
      return;
    }
    const section = sectionForTarget(target);
    selectWorkspaceSection(section);
    await ensureSection?.(section);
    if (target !== 'object') activeWorkspaceTarget.value = target;
    if (target === 'object') expandedSections.value.clientDetails = true;
    if (target === 'planning') {
      if (workflowType.value === 'sales_installation') expandedSections.value.proposals = true;
      if (status.value === 'execution') expandedSections.value.execution = true;
      else expandedSections.value.planningDetails = true;
    }
    if (target === 'proposal') expandedSections.value.proposals = true;
    if (target === 'documents') expandedSections.value.documents = true;
    if (target === 'payments') {
      if (status.value === 'execution') executionWorkspaceOpen.value = true;
      else expandedSections.value.payments = true;
    }
    await nextTick();
    if (target === 'documents') documentsWorkspaceRef.value?.openNative();
    if (target === 'equipment') {
      expandedSections.value.proposals = true;
      await equipmentPanelRef.value?.expand();
      await nextTick();
    }
    const elementId = status.value === 'execution' && target === 'payments'
      ? 'order-workspace-execution-details'
      : `order-workspace-${target}`;
    document.getElementById(elementId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return {
    activeWorkspaceTarget,
    activeWorkspaceSection,
    executionWorkspaceOpen,
    openWorkspaceTarget,
    resetWorkspaceNavigation,
    selectWorkspaceSection,
  };
};
