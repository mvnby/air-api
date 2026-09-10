import type { OrderWorkspaceUsageMetric } from '../services/order-workspace-usage-api';

const metricByControl: Record<string, OrderWorkspaceUsageMetric | undefined> = {
  'workspace-proposal': 'proposal_open',
  'workspace-documents': 'documents_open',
  'workspace-work': 'work_open',
  'workspace-payments': 'payments_open',
  'workspace-add-product': 'product_add',
  'context-object': 'object_edit',
  'context-payments': 'payments_open',
  equipment_open: 'equipment_open',
  attachments_open: 'attachments_open',
  'workflow-change': 'scenario_change',
  'autosave-toggle': 'autosave_toggle',
  order_product_add: 'product_add',
  order_product_select: 'product_select',
  order_product_fill_description: 'product_description_edit',
  order_product_description: 'product_description_edit',
  order_product_remove: 'product_remove',
  order_service_add: 'service_add',
  order_service_edit: 'service_edit',
  order_service_remove: 'service_remove',
  document_create: 'document_create',
  payment_add: 'payment_add',
  customer_open: 'customer_open',
};

export const useOrderWorkspaceUsageControls = (track: (metric: OrderWorkspaceUsageMetric) => void) => {
  const trackControl = (event: Event) => {
    if (!(event.target instanceof Element)) return;
    const control = event.target.closest('[data-order-usage]');
    const marker = control?.getAttribute('data-order-usage') || '';
    const metric = metricByControl[marker];
    if (!metric || !['click', 'change'].includes(event.type)) return;
    if (event.type === 'change' && !['workflow-change', 'order_product_description', 'order_service_edit'].includes(marker)) return;
    if (event.type === 'click' && ['workflow-change', 'order_product_description'].includes(marker)) return;
    if (event.type === 'click' && marker === 'order_service_edit' && control?.matches('input, textarea')) return;
    if (event.type === 'click' && ['equipment_open', 'attachments_open'].includes(marker) && control?.getAttribute('aria-expanded') === 'true') return;
    track(metric);
  };
  return { trackControl };
};
