import { OpenAPI, type ManagerOrderDocumentItem } from '../../../client';
import { getHeaders, request } from '../../../client/core/request';
import { getApiErrorMessage } from '../../../utils/api-errors';

export const EXTERNAL_DOCUMENT_TYPES = [
  { value: 'contract', label: 'Договор' },
  { value: 'technical_inspection_act', label: 'Акт технического обследования' },
  { value: 'defect_act', label: 'Дефектный акт' },
  { value: 'act', label: 'Акт оказанных услуг' },
  { value: 'other', label: 'Другой документ' },
] as const;

export type ExternalDocumentType = typeof EXTERNAL_DOCUMENT_TYPES[number]['value'];
export type ExternalDocumentStatus = 'received' | 'signed';
export type ExternalDocumentFileRole = 'original' | 'signed_copy';
export type ExternalFileVersion = {
  version: number;
  role: ExternalDocumentFileRole;
  filename: string;
  mime_type: string;
  size_bytes: number;
  checksum_sha256: string;
  uploaded_at: string;
  uploaded_by: string;
};
export type OrderDocumentWithEvidence = ManagerOrderDocumentItem & {
  origin?: 'legacy' | 'native_generated' | 'external_upload';
  external_status?: ExternalDocumentStatus | null;
  status?: string | null;
  file_version?: number;
  external_files?: ExternalFileVersion[];
};
export type ExternalDocumentSite = { id: number; title: string; address: string };
export type ExternalDocumentEquipment = {
  equipment_id: number;
  equipment: { display_name?: string | null; brand?: string | null; model?: string | null; serial?: string | null };
};
export type ExternalDocumentUpload = {
  document_type: ExternalDocumentType;
  number: string;
  document_date: string;
  external_status: ExternalDocumentStatus;
  site_id?: number;
  equipment_ids?: number[];
  base_document_id?: number;
  proposal_id?: number;
  file: File | null;
};

export const PRIVATE_DOCUMENT_FILE_ACCEPT = '.doc,.docx,.pdf';
export const EXTERNAL_DOCUMENT_MAX_BYTES = 10 * 1024 * 1024;
export const hasExternalOrigin = (document: ManagerOrderDocumentItem) =>
  (document as OrderDocumentWithEvidence).origin === 'external_upload';
export const matchesOrderDocumentSite = (document: ManagerOrderDocumentItem, siteId: number | null) =>
  siteId === null || document.scope_meta?.site_id === siteId
  || (Array.isArray(document.scope_meta?.site_ids) && document.scope_meta.site_ids.includes(siteId));

const orderPath = '/api/manager/orders/{order_id}';
const documentPath = '/api/manager/docs/{doc_id}';

export const externalOrderDocumentsApi = {
  list(orderId: number) {
    return request<{ items: OrderDocumentWithEvidence[] }>(OpenAPI, {
      method: 'GET', url: `${orderPath}/documents`, path: { order_id: orderId }, query: { include_native: true },
    });
  },
  sites(orderId: number) {
    return request<{ items: ExternalDocumentSite[] }>(OpenAPI, {
      method: 'GET', url: `${orderPath}/sites`, path: { order_id: orderId },
    });
  },
  equipment(orderId: number, siteId: number) {
    return request<{ items: ExternalDocumentEquipment[] }>(OpenAPI, {
      method: 'GET', url: `${orderPath}/sites/{site_id}/equipment`, path: { order_id: orderId, site_id: siteId },
    });
  },
  upload(orderId: number, value: ExternalDocumentUpload, key: string) {
    const formData = value.document_type === 'contract' && !value.file
      ? { number: value.number, contract_date: `${value.document_date}T00:00:00`, external_status: value.external_status }
      : value;
    return request<OrderDocumentWithEvidence>(OpenAPI, {
      method: 'POST',
      url: `${orderPath}/documents/${value.document_type === 'contract' && !value.file ? 'external-contract' : 'upload'}`,
      path: { order_id: orderId }, headers: { 'Idempotency-Key': key }, formData,
    });
  },
  attach(docId: number, role: ExternalDocumentFileRole, expectedVersion: number, file: File, key: string) {
    return request<OrderDocumentWithEvidence>(OpenAPI, {
      method: 'POST', url: `${documentPath}/file`, path: { doc_id: docId }, headers: { 'Idempotency-Key': key },
      formData: { file, file_role: role, expected_version: expectedVersion },
    });
  },
  async file(docId: number, version: number, signal: AbortSignal, previewPage?: number): Promise<Blob> {
    const route = `/api/manager/docs/${encodeURIComponent(docId)}/download`;
    const params = new URLSearchParams({ file_version: String(version) });
    if (previewPage !== undefined) {
      params.set('preview', 'true');
      params.set('preview_page', String(previewPage));
    }
    const headers = await getHeaders(OpenAPI, { method: 'GET', url: route, headers: { Accept: previewPage ? 'image/png' : '*/*' } });
    signal.throwIfAborted();
    const response = await fetch(`${OpenAPI.BASE}${route}?${params}`, {
      headers, signal, credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(getApiErrorMessage({ body, status: response.status }));
    }
    return response.blob();
  },
};
