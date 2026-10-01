import type { CancelablePromise } from '../client/core/CancelablePromise';
import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';
import type { ApiRequestOptions } from '../client/core/ApiRequestOptions';

export type SourceCommandHook = () => Promise<boolean | void>;
export type SourceCommandEndHook = () => void;

export type SourceCustomer = {
  name?: string | null;
  inn?: string | null;
  type?: 'individual' | 'individual_entrepreneur' | 'company' | null;
  phone?: string | null;
  email?: string | null;
  legal_address?: string | null;
};

export type SourceObject = {
  address: string;
  equipment: Array<{ brand?: string | null; model?: string | null; quantity?: number | null }>;
};

export type SourceScenario = {
  workflow_type: string;
  service_type?: string | null;
  label: string;
};

export type OrderSourcePreview = {
  order_id: number;
  source_code: string;
  external_id?: string | null;
  source_url?: string | null;
  title?: string | null;
  deadline_at?: string | null;
  estimated_value?: number | null;
  customer: SourceCustomer;
  existing_customer_id?: number | null;
  current_scenario?: SourceScenario | null;
  suggested_scenario?: SourceScenario | null;
  work_summary?: string | null;
  equipment_details?: string | null;
  objects: SourceObject[];
  documents: Array<{
    id: string;
    name: string;
    source_url?: string | null;
    extracted_text?: string | null;
    extracted_text_truncated?: boolean;
    download_url: string;
  }>;
  field_sources?: Record<string, string>;
  warnings: string[];
  analysis_source?: 'source' | 'ai' | 'reviewed';
  analyzed_document_ids?: string[];
  equipment_prefill?: SourceEquipmentPrefillResult | null;
};

export type SourceEquipmentPrefillResult = {
  proposal_id?: number | null;
  added: Array<{ model?: string | null; quantity?: number | null; product_id?: number | null; message: string }>;
  skipped: Array<{ model?: string | null; quantity?: number | null; product_id?: number | null; reason: string; message: string }>;
  warnings: string[];
};

export type SourceAppliedEvent = {
  orderId: number; customerId: number | null; appliedFields: string[]; customerAction: string;
  equipmentPrefill?: SourceEquipmentPrefillResult | null;
};

export type SourceEquipmentCandidate = {
  brand?: string | null; model?: string | null; quantity?: number | null;
  product_id?: number | null; product_title?: string | null;
  price?: number | null; available_quantity?: number | null; existing_quantity: number;
  reason: string; message: string; can_add: boolean; can_restore: boolean;
};
export type SourceEquipmentPreview = {
  order_id: number; proposal_id?: number | null; proposal_status?: string | null;
  preview_fingerprint: string; items: SourceEquipmentCandidate[]; warnings: string[];
};
export type SourceCard = {
  order_id: number; source: string; external_id: string; title?: string | null; source_url?: string | null;
  work_summary?: string | null; equipment_details?: string | null;
  objects: SourceObject[]; originals: Array<{ attachment_id: number; name: string; document_id?: string | null; mime_type: string }>;
  equipment_prefill?: SourceEquipmentPrefillResult | null;
  installation_facts: Array<{ text: string; source: string; needs_review: boolean; is_excerpt?: boolean }>;
};

export const downloadSourceOriginal = async (orderId: number, documentId: string, filename: string, stillCurrent?: () => boolean) => {
  const url = `/api/manager/orders/${encodeURIComponent(String(orderId))}/source-documents/${encodeURIComponent(documentId)}`;
  const options: ApiRequestOptions = { method: 'GET', url };
  const token = typeof OpenAPI.TOKEN === 'function' ? await OpenAPI.TOKEN(options) : OpenAPI.TOKEN;
  const configuredHeaders = typeof OpenAPI.HEADERS === 'function' ? await OpenAPI.HEADERS(options) : OpenAPI.HEADERS;
  const headers = new Headers(configuredHeaders);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${OpenAPI.BASE}${url}`, { headers, credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin' });
  if (!response.ok) throw new Error(`Не удалось скачать оригинал (${response.status})`);
  const blob = await response.blob();
  if (stillCurrent?.() === false) return;
  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = blobUrl; anchor.download = filename; anchor.rel = 'noopener noreferrer';
  document.body.appendChild(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1_000);
};

export const sourceEquipmentPrefillMessage = (result?: SourceEquipmentPrefillResult | null) => {
  if (!result) return '';
  const summary = result.added.length ? `В черновик добавлено позиций: ${result.added.length}.` : '';
  return [summary, ...result.warnings].filter(Boolean).join(' ');
};

export type OrderSourceApplyPayload = {
  customer_action: 'existing' | 'create' | 'skip';
  customer_id?: number;
  customer?: SourceCustomer;
  workflow_type?: string;
  service_type?: string | null;
  work_summary?: string;
  equipment_details?: string;
  objects?: SourceObject[];
  document_ids?: string[];
  analysis_source?: 'source' | 'ai' | 'reviewed';
  analyzed_document_ids?: string[];
};

export type OrderSourceApplyResult = {
  order_id: number;
  customer_id?: number | null;
  attachment_ids: number[];
  applied_fields: string[];
  equipment_prefill?: SourceEquipmentPrefillResult | null;
};

export const orderSourceReviewApi = {
  card(orderId: number): CancelablePromise<SourceCard> {
    return request(OpenAPI, { method: 'GET', url: '/api/manager/orders/{order_id}/source-card', path: { order_id: orderId } });
  },
  equipment(orderId: number, proposalId?: number | null): CancelablePromise<SourceEquipmentPreview> {
    return request(OpenAPI, { method: 'GET', url: '/api/manager/orders/{order_id}/source-equipment', path: { order_id: orderId }, query: { proposal_id: proposalId } });
  },
  addEquipment(orderId: number, payload: { proposal_id: number; command_id: string; preview_fingerprint: string; product_ids: number[]; restore_removed_product_ids: number[] }): CancelablePromise<SourceEquipmentPrefillResult> {
    return request(OpenAPI, { method: 'POST', url: '/api/manager/orders/{order_id}/source-equipment', path: { order_id: orderId }, mediaType: 'application/json', body: payload });
  },
  originalAccess(attachmentId: number): CancelablePromise<{ url: string }> {
    return request(OpenAPI, { method: 'GET', url: '/api/manager/service-attachments/{attachment_id}/access', path: { attachment_id: attachmentId }, query: { variant: 'original', download: true } });
  },
  preview(orderId: number): CancelablePromise<OrderSourcePreview> {
    return request(OpenAPI, {
      method: 'GET',
      url: '/api/manager/orders/{order_id}/source-preview',
      path: { order_id: orderId },
      errors: { 404: 'Not Found', 422: 'Validation Error' },
    });
  },
  apply(orderId: number, payload: OrderSourceApplyPayload): CancelablePromise<OrderSourceApplyResult> {
    return request(OpenAPI, {
      method: 'POST',
      url: '/api/manager/orders/{order_id}/source-apply',
      path: { order_id: orderId },
      mediaType: 'application/json',
      body: payload,
      errors: { 409: 'Conflict', 422: 'Validation Error' },
    });
  },
  analyze(orderId: number, documentIds: string[]): CancelablePromise<OrderSourcePreview> {
    return request(OpenAPI, {
      method: 'POST', url: '/api/manager/orders/{order_id}/source-analyze', path: { order_id: orderId },
      mediaType: 'application/json', body: { document_ids: documentIds }, errors: { 422: 'Validation Error' },
    });
  },
};
