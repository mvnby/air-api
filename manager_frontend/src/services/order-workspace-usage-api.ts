import {
  ManagerOrderUsageService,
  type OrderUsageDailyItem,
  type OrderUsageEvent,
  type OrderUsageReport,
} from '../client';
import type { CancelablePromise } from '../client/core/CancelablePromise';

export const ORDER_WORKSPACE_LAYOUT_VERSION = 'workspace_v1' as const;

export const ORDER_WORKSPACE_USAGE_METRICS = [
  'order_open', 'proposal_open', 'documents_open', 'work_open', 'payments_open',
  'customer_open', 'object_edit', 'equipment_open', 'attachments_open',
  'product_add', 'product_select', 'product_description_edit', 'product_remove',
  'service_add', 'service_edit', 'service_remove', 'scenario_change',
  'autosave_toggle', 'document_create', 'payment_add',
] as const;

export type OrderWorkspaceUsageMetric = OrderUsageEvent['metric'];
export type OrderWorkspaceUsageWorkflow = OrderUsageEvent['workflow'];
export type OrderWorkspaceUsageParty = OrderUsageEvent['party_kind'];
export type OrderWorkspaceUsageViewport = OrderUsageEvent['viewport'];
export type OrderWorkspaceUsageEvent = OrderUsageEvent;
export type OrderWorkspaceUsageReportItem = OrderUsageDailyItem;
export type OrderWorkspaceUsageReport = OrderUsageReport;

export type OrderWorkspaceUsageReportQuery = {
  days: 7 | 30 | 90;
  workflow?: OrderWorkspaceUsageWorkflow;
  party_kind?: OrderWorkspaceUsageParty;
  viewport?: OrderWorkspaceUsageViewport;
};

export const orderWorkspaceUsageApi = {
  record(events: OrderWorkspaceUsageEvent[]): CancelablePromise<{ accepted: number }> {
    return ManagerOrderUsageService.recordManagerOrderUsage({
      layout_version: ORDER_WORKSPACE_LAYOUT_VERSION,
      events,
    });
  },

  daily(query: OrderWorkspaceUsageReportQuery): CancelablePromise<OrderWorkspaceUsageReport> {
    return ManagerOrderUsageService.getManagerOrderUsage(
      query.days,
      query.workflow,
      query.party_kind,
      query.viewport,
    );
  },
};
