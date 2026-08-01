import { computed, ref, type Ref } from 'vue';
import type {
  ManagerOrderDetailResponse,
  OrderProductLineResponse,
  OrderProposalResponse,
  OrderServiceLineResponse,
} from '../client';
import { ManagerOrdersService } from '../client';
import { confirmDialog, promptDialog } from '../services/ui-feedback';
import { getApiErrorMessage } from '../utils/api-errors';
import { formatMoney } from '../components/orders/order-utils';
import {
  isProposalRevisionLocked,
  normalizeProposalStatus,
  proposalStatusLabel,
  type ProposalLifecycleStatus,
} from '../components/orders/proposal-lifecycle';

type ToastHandler = (message: string, type?: 'success' | 'error') => void;

type UseOrderProposalLifecycleOptions = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  negotiationStatus: Ref<string>;
  total: Readonly<Ref<number>>;
  localFormError: Ref<string>;
  buildLinesPayload: (proposalId: number | null) => Record<string, unknown>;
  validateLines: () => string;
  loadLines: (products: OrderProductLineResponse[], services: OrderServiceLineResponse[]) => void;
  resetLookupState: () => void;
  loadSupplyRequests: (orderId: number) => Promise<void>;
  clearDraft: () => void;
  currentLinesSnapshot: (proposalId: number | null) => string;
  savedLinesSnapshot: Ref<string>;
  setToast: ToastHandler;
  onUpdated: (order: ManagerOrderDetailResponse) => void;
  onReload: (orderId: number) => void;
};

export const useOrderProposalLifecycle = ({
  order,
  negotiationStatus,
  total,
  localFormError,
  buildLinesPayload,
  validateLines,
  loadLines,
  resetLookupState,
  loadSupplyRequests,
  clearDraft,
  currentLinesSnapshot,
  savedLinesSnapshot,
  setToast,
  onUpdated,
  onReload,
}: UseOrderProposalLifecycleOptions) => {
  const proposalStatus = ref<ProposalLifecycleStatus>('draft');
  const activeProposalId = ref<number | null>(null);
  const proposalActionLoading = ref(false);

  const proposals = computed(() => [...(order.value?.proposals || [])]
    .filter((proposal) => !proposal.is_archived)
    .sort((left, right) => (
      Number(left.sort_order || 0) - Number(right.sort_order || 0)
      || Number(left.id) - Number(right.id)
    )));
  const selectedProposal = computed(() => (
    proposals.value.find((proposal) => proposal.is_selected)
    || proposals.value[0]
    || null
  ));
  const activeProposal = computed(() => (
    proposals.value.find((proposal) => proposal.id === activeProposalId.value)
    || selectedProposal.value
  ));
  const activeProposalStatus = computed(() => (
    normalizeProposalStatus(activeProposal.value?.status || proposalStatus.value)
  ));
  const activeProposalLocked = computed(() => isProposalRevisionLocked(activeProposalStatus.value));
  const activeProposalLineLabel = computed(() => {
    const proposal = activeProposal.value;
    if (!proposal) return 'Предложение не создано';
    const count = (proposal.product_lines?.length || 0) + (proposal.service_lines?.length || 0);
    const mod100 = count % 100;
    const mod10 = count % 10;
    const noun = mod100 >= 11 && mod100 <= 14
      ? 'позиций'
      : mod10 === 1
        ? 'позиция'
        : mod10 >= 2 && mod10 <= 4
          ? 'позиции'
          : 'позиций';
    return `${proposal.name} · ${proposalStatusLabel(proposal.status)} · ${count} ${noun} · ${formatMoney(proposal.total_amount || 0)}`;
  });

  const loadProposalLines = (
    proposal: OrderProposalResponse | null | undefined,
    fallbackOrder?: ManagerOrderDetailResponse | null,
  ) => {
    if (proposal) {
      activeProposalId.value = proposal.id;
      proposalStatus.value = normalizeProposalStatus(proposal.status);
      loadLines(proposal.product_lines || [], proposal.service_lines || []);
      return;
    }
    activeProposalId.value = null;
    loadLines(fallbackOrder?.product_lines ?? [], fallbackOrder?.service_lines ?? []);
  };

  const applyOrderResponse = async (
    updatedOrder: ManagerOrderDetailResponse,
    preferredProposalId?: number | null,
    emitReload = true,
  ) => {
    onUpdated(updatedOrder);
    const nextProposal = preferredProposalId
      ? (updatedOrder.proposals || []).find((proposal) => proposal.id === preferredProposalId && !proposal.is_archived)
      : ((updatedOrder.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
        || (updatedOrder.proposals || []).find((proposal) => !proposal.is_archived));
    loadProposalLines(nextProposal || null, updatedOrder);
    resetLookupState();
    await loadSupplyRequests(updatedOrder.id);
    if (emitReload) onReload(updatedOrder.id);
  };

  const saveCurrentProposalLines = async () => {
    if (!order.value?.id) return order.value || null;
    if (activeProposalLocked.value) return order.value;
    const validationError = validateLines();
    if (validationError) {
      localFormError.value = validationError;
      throw new Error(validationError);
    }
    const currentProposalId = activeProposalId.value;
    const updatedOrder = await ManagerOrdersService.patchManagerOrder(
      order.value.id,
      buildLinesPayload(currentProposalId),
    );
    clearDraft();
    await applyOrderResponse(updatedOrder, currentProposalId, false);
    savedLinesSnapshot.value = currentLinesSnapshot(activeProposalId.value);
    return updatedOrder;
  };

  const setActiveProposal = async (proposal: OrderProposalResponse) => {
    if (!proposal || activeProposalId.value === proposal.id || proposalActionLoading.value) return;
    proposalActionLoading.value = true;
    try {
      await saveCurrentProposalLines();
    } catch (error) {
      setToast(`Сначала сохраните текущий вариант: ${getApiErrorMessage(error)}`, 'error');
      return;
    } finally {
      proposalActionLoading.value = false;
    }
    loadProposalLines(proposal, order.value);
    resetLookupState();
  };

  const createProposal = async () => {
    if (!order.value?.id || proposalActionLoading.value) return;
    const name = await promptDialog({
      title: 'Новое предложение',
      inputLabel: 'Название',
      initialValue: `Вариант ${proposals.value.length + 1}`,
      required: true,
      confirmText: 'Создать',
    });
    if (name === null) return;
    proposalActionLoading.value = true;
    try {
      await saveCurrentProposalLines();
      const updatedOrder = await ManagerOrdersService.createManagerOrderProposal(order.value.id, { name });
      const created = updatedOrder.proposals?.[Math.max(0, (updatedOrder.proposals?.length || 1) - 1)] || null;
      await applyOrderResponse(updatedOrder, created?.id || null);
      setToast('Предложение создано', 'success');
    } catch (error) {
      setToast(`Ошибка создания предложения: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      proposalActionLoading.value = false;
    }
  };

  const duplicateProposal = async () => {
    if (!order.value?.id || !activeProposal.value?.id || proposalActionLoading.value) return;
    const name = await promptDialog({
      title: 'Копия предложения',
      inputLabel: 'Название',
      initialValue: `${activeProposal.value.name} копия`,
      required: true,
      confirmText: 'Создать копию',
    });
    if (name === null) return;
    proposalActionLoading.value = true;
    try {
      const sourceProposalId = activeProposal.value.id;
      await saveCurrentProposalLines();
      const updatedOrder = await ManagerOrdersService.duplicateManagerOrderProposal(order.value.id, sourceProposalId, { name });
      const created = updatedOrder.proposals?.[Math.max(0, (updatedOrder.proposals?.length || 1) - 1)] || null;
      await applyOrderResponse(updatedOrder, created?.id || null);
      setToast('Предложение скопировано', 'success');
    } catch (error) {
      setToast(`Ошибка копирования предложения: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      proposalActionLoading.value = false;
    }
  };

  const renameProposal = async () => {
    if (!order.value?.id || !activeProposal.value?.id || proposalActionLoading.value) return;
    const name = await promptDialog({
      title: 'Переименовать предложение',
      inputLabel: 'Название',
      initialValue: activeProposal.value.name,
      required: true,
      confirmText: 'Переименовать',
    });
    if (name === null || !name.trim()) return;
    proposalActionLoading.value = true;
    try {
      const proposalId = activeProposal.value.id;
      await saveCurrentProposalLines();
      const updatedOrder = await ManagerOrdersService.patchManagerOrderProposal(order.value.id, proposalId, { name });
      await applyOrderResponse(updatedOrder, proposalId);
      setToast('Название обновлено', 'success');
    } catch (error) {
      setToast(`Ошибка переименования: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      proposalActionLoading.value = false;
    }
  };

  const archiveProposal = async () => {
    if (!order.value?.id || !activeProposal.value?.id || proposalActionLoading.value) return;
    if (proposals.value.length <= 1) {
      setToast('Нельзя удалить единственное предложение', 'error');
      return;
    }
    if (!await confirmDialog({
      title: 'Архивировать предложение?',
      description: activeProposal.value.name,
      confirmText: 'Архивировать',
      variant: 'warning',
    })) return;
    const archivedId = activeProposal.value.id;
    proposalActionLoading.value = true;
    try {
      const updatedOrder = await ManagerOrdersService.archiveManagerOrderProposal(order.value.id, archivedId);
      const next = (updatedOrder.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
        || (updatedOrder.proposals || []).find((proposal) => proposal.id !== archivedId && !proposal.is_archived)
        || null;
      await applyOrderResponse(updatedOrder, next?.id || null);
      setToast('Предложение архивировано', 'success');
    } catch (error) {
      setToast(`Ошибка архивации: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      proposalActionLoading.value = false;
    }
  };

  const selectProposalForOrder = async (proposal?: OrderProposalResponse) => {
    const target = proposal || activeProposal.value;
    if (!order.value?.id || !target?.id || target.is_selected || proposalActionLoading.value) return;
    proposalActionLoading.value = true;
    try {
      await saveCurrentProposalLines();
      const updatedOrder = await ManagerOrdersService.selectManagerOrderProposal(order.value.id, target.id);
      await applyOrderResponse(updatedOrder, target.id);
      setToast('Предложение выбрано для заказа', 'success');
    } catch (error) {
      setToast(`Ошибка выбора предложения: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      proposalActionLoading.value = false;
    }
  };

  const changeActiveProposalStatus = async (nextStatus: ProposalLifecycleStatus) => {
    const proposal = activeProposal.value;
    if (!order.value?.id || !proposal?.id || proposalActionLoading.value) return;
    if (nextStatus === activeProposalStatus.value) return;
    if (nextStatus === 'ready_to_send') {
      const validationError = validateLines();
      if (validationError || total.value <= 0) {
        setToast(validationError || 'Добавьте хотя бы одну позицию с ненулевой суммой', 'error');
        return;
      }
    }
    if (nextStatus === 'sent' && !await confirmDialog({
      title: 'Отметить предложение отправленным?',
      description: 'Используйте это действие, если предложение отправлено не через CRM. Для email используйте основную кнопку отправки.',
      confirmText: 'Отметить отправленным',
      variant: 'warning',
    })) return;
    if (nextStatus === 'draft' && activeProposalLocked.value && !await confirmDialog({
      title: 'Вернуть предложение в черновик?',
      description: 'После этого предложение снова можно будет редактировать.',
      confirmText: 'Вернуть в черновик',
      variant: 'warning',
    })) return;
    proposalActionLoading.value = true;
    try {
      if (nextStatus === 'ready_to_send') await saveCurrentProposalLines();
      const updatedOrder = await ManagerOrdersService.patchManagerOrderProposal(order.value.id, proposal.id, { status: nextStatus });
      proposalStatus.value = nextStatus;
      negotiationStatus.value = updatedOrder.negotiation_status || negotiationStatus.value;
      await applyOrderResponse(updatedOrder, proposal.id);
      setToast(`Статус предложения: ${proposalStatusLabel(nextStatus)}`, 'success');
    } catch (error) {
      setToast(`Не удалось изменить статус: ${getApiErrorMessage(error)}`, 'error');
    } finally {
      proposalActionLoading.value = false;
    }
  };

  return {
    activeProposal,
    activeProposalId,
    activeProposalLineLabel,
    activeProposalLocked,
    activeProposalStatus,
    archiveProposal,
    changeActiveProposalStatus,
    createProposal,
    duplicateProposal,
    loadProposalLines,
    onProposalClick: (proposal: OrderProposalResponse) => void setActiveProposal(proposal),
    proposalActionLoading,
    proposalStatus,
    proposals,
    renameProposal,
    saveCurrentProposalLines,
    selectProposalForOrder,
    selectedProposal,
  };
};
