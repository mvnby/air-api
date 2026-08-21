import type { ManagerOrderDetailResponse } from '../client';

export type CatalogDecisionAttachMode = 'auto' | 'replace_selected' | 'new_alternative';

export const hasActiveOrderProducts = (order: ManagerOrderDetailResponse | null): boolean => (
  (order?.proposals || []).some(
    proposal => !proposal.is_archived && Boolean(proposal.product_lines?.length),
  )
);

export const defaultCatalogDecisionAttachMode = (
  order: ManagerOrderDetailResponse | null,
): CatalogDecisionAttachMode => (hasActiveOrderProducts(order) ? 'new_alternative' : 'auto');
