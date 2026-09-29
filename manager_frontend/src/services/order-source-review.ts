import type { CancelablePromise } from '../client/core/CancelablePromise';
import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';

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
};

export const orderSourceReviewApi = {
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
