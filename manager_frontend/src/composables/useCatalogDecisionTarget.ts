import { computed, ref } from 'vue';
import { ManagerCatalogDecisionService, ManagerOrdersService, type ManagerOrderDetailResponse } from '../client';
import { readCatalogDecisionContext, type CatalogDecisionOrderContext } from '../services/catalog-decision-context';
import { getApiErrorMessage } from '../utils/api-errors';
import { isProposalRevisionLocked } from '../components/orders/proposal-lifecycle';

export const useCatalogDecisionTarget = () => {
  const context = ref<CatalogDecisionOrderContext | null>(null);
  const order = ref<ManagerOrderDetailResponse | null>(null);
  const error = ref('');
  const loading = ref(false);
  const saving = ref(false);
  try { context.value = readCatalogDecisionContext(window.location.search); }
  catch (err) { error.value = (err as Error).message; }
  const requested = Boolean(context.value || error.value);
  const proposal = computed(() => order.value?.proposals?.find(item => item.id === context.value?.proposalId && !item.is_archived));
  const canAttach = computed(() => Boolean(context.value && order.value?.status === 'negotiation' && proposal.value && !isProposalRevisionLocked(proposal.value.status) && !loading.value));
  const load = async () => {
    if (!context.value) return;
    loading.value = true;
    error.value = '';
    try {
      order.value = await ManagerOrdersService.getManagerOrderDetail(context.value.orderId);
      if (order.value.status !== 'negotiation') error.value = 'Заказ уже не в переговорах. Вернитесь в заказ и проверьте его состояние.';
      else if (!proposal.value) error.value = 'Вариант предложения больше недоступен. Откройте подбор из нужного варианта заказа.';
      else if (isProposalRevisionLocked(proposal.value.status)) error.value = 'Этот вариант уже нельзя редактировать. Создайте копию или верните его в черновик в заказе.';
    } catch (err) {
      order.value = null;
      error.value = getApiErrorMessage(err) || 'Не удалось загрузить заказ для подбора';
    } finally { loading.value = false; }
  };
  const attach = async (productIds: number[]): Promise<boolean> => {
    if (!context.value || !canAttach.value || saving.value || !productIds.length) return false;
    saving.value = true;
    error.value = '';
    try {
      await ManagerCatalogDecisionService.attachManagerCatalogDecisionToOrder(context.value.orderId, {
        product_ids: productIds, mode: 'append_to_proposal', proposal_id: context.value.proposalId,
      });
      return true;
    } catch (err) {
      const message = getApiErrorMessage(err) || 'Не удалось добавить модели в заказ';
      await load();
      error.value = message;
      return false;
    } finally { saving.value = false; }
  };
  return { requested, context, order, proposal, error, loading, saving, canAttach, load, attach };
};
