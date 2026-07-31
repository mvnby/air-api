import { nextTick, ref, type Ref } from 'vue';
import type { ManagerOrderDocumentItem, OrderProposalResponse } from '../client';
import type { OrderDrawerSectionsState } from './useOrderDrawerPersistence';
import type { OrderWorkflowType, OrderWorkspaceTarget } from '../components/orders/order-workspace';

type ToastHandler = (message: string, type?: 'success' | 'error') => void;
type EquipmentPanelHandle = { collapse: () => void; expand: () => Promise<void> | void };
type DocumentsWorkspaceHandle = { openSend: () => void; openCreate: () => void };

type UseOrderWorkspaceNavigationOptions = {
  status: Readonly<Ref<string>>;
  workflowType: Readonly<Ref<OrderWorkflowType>>;
  expandedSections: Ref<OrderDrawerSectionsState>;
  equipmentPanelRef: Ref<EquipmentPanelHandle | null>;
  documentsWorkspaceRef: Ref<DocumentsWorkspaceHandle | null>;
  setToast: ToastHandler;
};

export const useOrderWorkspaceNavigation = ({
  status,
  workflowType,
  expandedSections,
  equipmentPanelRef,
  documentsWorkspaceRef,
  setToast,
}: UseOrderWorkspaceNavigationOptions) => {
  const executionWorkspaceOpen = ref(false);
  const activeWorkspaceTarget = ref<OrderWorkspaceTarget | null>(null);

  const resetWorkspaceNavigation = () => {
    executionWorkspaceOpen.value = false;
    activeWorkspaceTarget.value = null;
  };

  const openWorkspaceTarget = async (target: OrderWorkspaceTarget, allowToggle = false) => {
    const shouldClose = allowToggle && activeWorkspaceTarget.value === target;
    if (activeWorkspaceTarget.value === 'equipment') equipmentPanelRef.value?.collapse();
    if (workflowType.value === 'sales_installation' && target !== 'object') {
      expandedSections.value.proposals = false;
      expandedSections.value.documents = false;
      expandedSections.value.payments = false;
      expandedSections.value.execution = false;
      executionWorkspaceOpen.value = false;
    }
    if (shouldClose) {
      activeWorkspaceTarget.value = null;
      return;
    }
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

  const openProposalSend = async (
    proposal: OrderProposalResponse | null | undefined,
    documents: ManagerOrderDocumentItem[],
  ) => {
    if (!proposal) return;
    expandedSections.value.documents = true;
    activeWorkspaceTarget.value = 'documents';
    await nextTick();
    const offerExists = documents.some((document) => (
      document.doc_type === 'offer'
      && (!document.proposal_id || document.proposal_id === proposal.id)
    ));
    if (offerExists) documentsWorkspaceRef.value?.openSend();
    else {
      documentsWorkspaceRef.value?.openCreate();
      setToast('Сначала создайте коммерческое предложение для активного варианта', 'error');
    }
    document.getElementById('order-workspace-documents')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const openDocumentsSend = async () => {
    expandedSections.value.documents = true;
    activeWorkspaceTarget.value = 'documents';
    await nextTick();
    documentsWorkspaceRef.value?.openSend();
    document.getElementById('order-workspace-documents')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return {
    activeWorkspaceTarget,
    executionWorkspaceOpen,
    openDocumentsSend,
    openProposalSend,
    openWorkspaceTarget,
    resetWorkspaceNavigation,
  };
};
