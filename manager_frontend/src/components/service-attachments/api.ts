import { OpenAPI } from '../../client/core/OpenAPI';
import type { ApiRequestOptions } from '../../client/core/ApiRequestOptions';
import type {
  ServiceAttachmentAccessResponse,
  ServiceAttachmentCategory,
  ServiceAttachmentItem,
  ServiceAttachmentListResponse,
  ServiceAttachmentUpdatePayload,
  ServiceAttachmentVariant,
} from './types';

type RequestOptions = {
  method?: ApiRequestOptions['method'];
  body?: BodyInit | null;
  headers?: Record<string, string>;
};

const resolveToken = async (method: ApiRequestOptions['method'], url: string) => {
  if (typeof OpenAPI.TOKEN === 'function') return OpenAPI.TOKEN({ method, url });
  return OpenAPI.TOKEN;
};

const extractErrorMessage = (payload: unknown, fallback: string) => {
  if (!payload || typeof payload !== 'object') return fallback;
  const record = payload as Record<string, unknown>;
  const detail = record.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as Record<string, unknown>).message;
    if (typeof message === 'string') return message;
  }
  if (typeof record.message === 'string') return record.message;
  return fallback;
};

const request = async <T>(path: string, options: RequestOptions = {}): Promise<T> => {
  const method = options.method || 'GET';
  const token = await resolveToken(method, path);
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...options.headers,
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    method,
    body: options.body,
    headers,
    credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
  });

  const responseText = response.status === 204 ? '' : await response.text();

  if (!response.ok) {
    const fallback = `Ошибка запроса (${response.status})`;
    let payload: unknown = null;
    try {
      payload = responseText ? JSON.parse(responseText) : null;
    } catch {
      if (responseText) throw new Error(responseText);
    }
    throw new Error(extractErrorMessage(payload, fallback));
  }

  if (!responseText) return undefined as T;
  return JSON.parse(responseText) as T;
};

export const serviceAttachmentsApi = {
  list(orderId: number) {
    return request<ServiceAttachmentListResponse>(`/api/manager/orders/${encodeURIComponent(String(orderId))}/attachments`);
  },

  upload(
    orderId: number,
    file: File,
    options: {
      category: ServiceAttachmentCategory | string;
      caption?: string;
      equipmentId?: number | null;
      componentId?: number | null;
    },
  ) {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('category', options.category);
    if (options.caption?.trim()) form.append('caption', options.caption.trim());
    if (options.equipmentId) form.append('equipment_id', String(options.equipmentId));
    if (options.componentId) form.append('component_id', String(options.componentId));
    return request<ServiceAttachmentItem>(`/api/manager/orders/${encodeURIComponent(String(orderId))}/attachments`, {
      method: 'POST',
      body: form,
    });
  },

  update(orderId: number, attachmentId: number, payload: ServiceAttachmentUpdatePayload) {
    return request<ServiceAttachmentItem>(`/api/manager/service-attachments/${encodeURIComponent(String(attachmentId))}`, {
      method: 'PATCH',
      body: JSON.stringify({ ...payload, order_id: orderId }),
      headers: { 'Content-Type': 'application/json' },
    });
  },

  remove(orderId: number, attachmentId: number) {
    const query = new URLSearchParams({ order_id: String(orderId) });
    return request<void>(`/api/manager/service-attachments/${encodeURIComponent(String(attachmentId))}?${query.toString()}`, {
      method: 'DELETE',
    });
  },

  getAccess(attachmentId: number, variant: ServiceAttachmentVariant) {
    const query = new URLSearchParams({ variant });
    return request<ServiceAttachmentAccessResponse>(
      `/api/manager/service-attachments/${encodeURIComponent(String(attachmentId))}/access?${query.toString()}`,
    );
  },
};
