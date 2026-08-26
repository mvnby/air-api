import { computed, ref, type ComputedRef } from 'vue';
import { ManagerOrdersService, type ManagerOrderDetailResponse, type OrderProposalResponse } from '../../../client';
import { getApiErrorMessage } from '../../../utils/api-errors';
import type { WaybillProductLine } from '../model/document-types';
import {
  cloneWaybillProductLine,
  ensureWaybillComponents,
  hasUsableWaybillProductLine,
  mapOrderProductLineToWaybillLine,
} from '../model/waybill-logistics';

type WaybillScopeInput = {
  order: () => ManagerOrderDetailResponse;
  productLines: () => WaybillProductLine[];
  selectedProposal: ComputedRef<OrderProposalResponse | null>;
  activeProposalId: () => number | null;
  notify: (message: string, type?: 'success' | 'error') => void;
};

export const useWaybillDocumentScope = (input: WaybillScopeInput) => {
  const lines = ref<WaybillProductLine[]>([]);
  const proposalId = computed(() => input.activeProposalId() ?? input.selectedProposal.value?.id ?? null);
  const resolvedLines = computed(() => {
    const passed = input.productLines();
    const proposal = input.selectedProposal.value;
    const fallback = proposal?.product_lines?.length
      ? proposal.product_lines.map(mapOrderProductLineToWaybillLine)
      : (input.order().product_lines || []).map(mapOrderProductLineToWaybillLine);
    return (passed.some(hasUsableWaybillProductLine) ? passed : fallback).filter(hasUsableWaybillProductLine);
  });
  const sync = () => { lines.value = resolvedLines.value.map(cloneWaybillProductLine); };
  const ensureComponents = () => lines.value.forEach(ensureWaybillComponents);
  const save = async () => {
    if (!lines.value.length) return true;
    if (lines.value.some((line) => !Number(line.product_id || 0))) {
      input.notify('Для накладной выберите товар из каталога в товарной строке.', 'error');
      return false;
    }
    try {
      await ManagerOrdersService.patchManagerOrder(input.order().id, {
        products: lines.value.map((line) => ({
          product_id: Number(line.product_id),
          quantity: Math.trunc(Number(line.quantity) || 0),
          price: Math.round(Number(line.price) || 0),
          cost: line.cost == null ? null : Math.round(Number(line.cost) || 0),
          proposal_id: proposalId.value ?? undefined,
          logistics_components: line.logistics_components?.length ? line.logistics_components : null,
        })),
      });
      return true;
    } catch (error) {
      input.notify(`Ошибка сохранения состава накладной: ${getApiErrorMessage(error)}`, 'error');
      return false;
    }
  };

  return { ensureComponents, lines, proposalId, save, sync };
};
