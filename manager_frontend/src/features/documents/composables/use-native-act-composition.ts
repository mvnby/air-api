import { computed, watch, type ComputedRef } from 'vue';
import type { ManagerOrderDetailResponse } from '../../../client';
import { useActDocumentScope } from './use-act-document-scope';

export function useNativeActComposition(
  order: () => ManagerOrderDetailResponse,
  proposalId: ComputedRef<number | null>,
  notify: (message: string, type?: 'success' | 'error') => void,
) {
  const lines = computed(() => {
    const id = proposalId.value;
    if (id === null) return order().service_lines || [];
    const proposal = order().proposals?.find((item) => item.id === id && !item.is_archived);
    if (!proposal) return [];
    return proposal.service_lines ?? (order().service_lines || []).filter((line) => line.proposal_id === id);
  });
  const scope = useActDocumentScope({ order, activeServiceLines: lines, notify });
  watch([() => order().id, () => order().customer?.id, proposalId], () => {
    scope.reset();
  }, { immediate: true });
  watch(lines, () => {
    // Keep a partial selection across an order save; never expand it to new/removed rows.
    const quantities = scope.selectedServiceLineQuantities.value;
    const next = Object.fromEntries(lines.value
      .filter((line) => quantities[line.id] && scope.maxQuantity(line) > 0)
      .map((line) => [line.id, Math.min(quantities[line.id]!, scope.maxQuantity(line))]));
    scope.selectedServiceLineQuantities.value = next;
    scope.selectedServiceLineIds.value = Object.keys(next).map(Number);
  });
  const payload = computed(() => ({
    scope_customer_branch_id: scope.selectedBranchId.value,
    scope_title: scope.title.value.trim() || null,
    scope_address: scope.address.value.trim() || null,
    scope_service_line_ids: scope.selectedServiceLineIds.value,
    scope_service_line_quantities: scope.selectedServiceLineQuantities.value,
  }));
  const total = computed(() => lines.value.reduce((sum, line) => sum + line.price * scope.quantity(line.id), 0));
  return { ...scope, lines, payload, total };
}
