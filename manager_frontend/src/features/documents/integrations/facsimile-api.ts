import { OpenAPI } from '../../../client';
import type { ApiRequestOptions } from '../../../client/core/ApiRequestOptions';
import type { FacsimilePreview, FacsimileSave } from '../model/facsimile-placement';

const documentPath = (documentId: number) => `/api/manager/document-system/documents/${encodeURIComponent(String(documentId))}`;
const request = async (path: string, method: ApiRequestOptions['method'], signal: AbortSignal, body?: FacsimileSave) => {
  const token = typeof OpenAPI.TOKEN === 'function' ? await OpenAPI.TOKEN({ method, url: path }) : OpenAPI.TOKEN;
  signal.throwIfAborted();
  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    method,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body ? { 'Content-Type': 'application/json' } : {}) },
    credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
    signal,
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail?.message || payload?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Ошибка запроса (${response.status})`);
  }
  return response;
};
export const facsimileApi = {
  async preview(documentId: number, signal: AbortSignal): Promise<FacsimilePreview> {
    return (await request(`${documentPath(documentId)}/facsimile-preview`, 'GET', signal)).json();
  },
  async page(documentId: number, page: number, signal: AbortSignal): Promise<Blob> {
    return (await request(`${documentPath(documentId)}/facsimile-preview/pages/${page}`, 'GET', signal)).blob();
  },
  async asset(documentId: number, assetId: string, signal: AbortSignal): Promise<Blob> {
    return (await request(`${documentPath(documentId)}/facsimile-preview/assets/${encodeURIComponent(assetId)}`, 'GET', signal)).blob();
  },
  async save(documentId: number, payload: FacsimileSave, signal: AbortSignal): Promise<{ id: string; kind: string; filename: string }> {
    return (await request(`${documentPath(documentId)}/facsimile-pdf`, 'POST', signal, payload)).json();
  },
};
