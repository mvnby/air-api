import { OpenAPI } from '../client';
import { request } from '../client/core/request';
import type { BusinessDocumentTerms } from '../features/documents/model/business-document-terms';

export type CommercialSourceTerm = {
  kind: 'payment' | 'delivery';
  source: string;
  evidence: string;
  share_percent: number | string | null;
  due_days: number | null;
  day_kind: 'calendar' | 'banking' | 'working' | null;
  due_event: string | null;
  trigger_text: string | null;
  deadline: string | null;
  issues: string[];
};
export type CommercialTerms = {
  order_id: number;
  revision: number;
  customer_requested: CommercialSourceTerm[];
  proposed: Partial<BusinessDocumentTerms> | null;
  suggested: Partial<BusinessDocumentTerms> | null;
  confirmed: boolean;
  warnings: string[];
};
export const commercialTermsApi = {
  read: (orderId: number) => request<CommercialTerms>(OpenAPI, {
    method: 'GET', url: '/api/manager/orders/{order_id}/commercial-terms', path: { order_id: orderId },
  }),
  update: (orderId: number, revision: number, proposed: BusinessDocumentTerms, confirmed: boolean) => request<CommercialTerms>(OpenAPI, {
    method: 'PATCH', url: '/api/manager/orders/{order_id}/commercial-terms', path: { order_id: orderId },
    body: { expected_revision: revision, proposed, confirmed }, mediaType: 'application/json',
  }),
  extract: (orderId: number, attachmentIds: number[]) => request<CommercialTerms>(OpenAPI, {
    method: 'POST', url: '/api/manager/orders/{order_id}/commercial-terms/extract', path: { order_id: orderId },
    body: { attachment_ids: attachmentIds }, mediaType: 'application/json',
  }),
  defaults: (orderId: number) => request<{ order_id: number; revision: number; business_terms: Partial<BusinessDocumentTerms> | null }>(OpenAPI, {
    method: 'GET', url: '/api/manager/orders/{order_id}/commercial-terms/document-defaults', path: { order_id: orderId },
  }),
};

/** Fill only fields unchanged since the request started. Manual form edits win. */
export const mergeCommercialDocumentDefaults = (
  current: BusinessDocumentTerms,
  baseline: BusinessDocumentTerms,
  defaults: Partial<BusinessDocumentTerms>,
): BusinessDocumentTerms => {
  const next = { ...current };
  for (const key of Object.keys(defaults) as Array<keyof BusinessDocumentTerms>) {
    if (JSON.stringify(current[key]) === JSON.stringify(baseline[key])) {
      if (key === 'contract_scenario' && !defaults[key]) continue;
      const value = key === 'payment_schedule'
        ? defaults.payment_schedule?.map((item) => ({ ...item, share_percent: Number(item.share_percent) }))
        : defaults[key];
      Object.assign(next, { [key]: value });
    }
  }
  return next;
};
