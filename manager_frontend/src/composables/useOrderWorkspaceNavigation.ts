import { nextTick, ref, type Ref } from 'vue';
import type { OrderDrawerSectionsState } from './useOrderDrawerPersistence';
import type { OrderWorkflowType, OrderWorkspaceTarget } from '../components/orders/order-workspace';
import type { OrderWorkspaceSection } from '../components/orders/OrderWorkspaceNav.vue';

type EquipmentPanelHandle = { collapse: () => void; expand: () => Promise<void> | void };
type DocumentsWorkspaceHandle = { openNative: () => void };

type UseOrderWorkspaceNavigationOptions = {
  status: Readonly<Ref<string>>;
  workflowType: Readonly<Ref<OrderWorkflowType>>;
  expandedSections: Ref<OrderDrawerSectionsState>;
  equipmentPanelRef: Ref<EquipmentPanelHandle | null>;
  documentsWorkspaceRef: Ref<DocumentsWorkspaceHandle | null>;
};

export const useOrderWorkspaceNavigation = ({
  status,
  workflowType,
  expandedSections,
  equipmentPanelRef,
  documentsWorkspaceRef,
}: UseOrderWorkspaceNavigationOptions) => {
  const executionWorkspaceOpen = ref(false);
  const activeWorkspaceTarget = ref<OrderWorkspaceTarget | null>(null);
  const activeWorkspaceSection = ref<OrderWorkspaceSection>('proposal');

  const sectionForTarget = (target: OrderWorkspaceTarget): OrderWorkspaceSection => {
    if (target === 'proposal') return 'proposal';
    if (target === 'documents') return 'documents';
    if (target === 'payments') return 'payments';
    return 'work';
  };

  const selectWorkspaceSection = (section: OrderWorkspaceSection) => {
    activeWorkspaceSection.value = section;
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
    activeWorkspaceSection.value = 'proposal';
  };

  const openWorkspaceTarget = async (target: OrderWorkspaceTarget, allowToggle = false) => {
    const shouldClose = allowToggle && activeWorkspaceTarget.value === target;
    if (activeWorkspaceTarget.value === 'equipment') equipmentPanelRef.value?.collapse();
    if (shouldClose) {
      activeWorkspaceTarget.value = null;
      return;
    }
    selectWorkspaceSection(sectionForTarget(target));
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
