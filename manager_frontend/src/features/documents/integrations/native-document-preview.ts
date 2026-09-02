import { OpenAPI } from '../../../client';
import type { ApiRequestOptions } from '../../../client/core/ApiRequestOptions';

const resolveToken = async (method: ApiRequestOptions['method'], url: string) => {
  if (typeof OpenAPI.TOKEN === 'function') return OpenAPI.TOKEN({ method, url });
  return OpenAPI.TOKEN;
};

export const openNativeDocumentPreview = async (documentId: number) => {
  const path = `/api/manager/document-system/documents/${encodeURIComponent(String(documentId))}/preview`;
  const popup = window.open('about:blank', '_blank');
  if (popup) popup.opener = null;
  try {
    const token = await resolveToken('GET', path);
    const response = await fetch(`${OpenAPI.BASE}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.detail?.message || payload?.detail;
      throw new Error(typeof detail === 'string' ? detail : `Ошибка запроса (${response.status})`);
    }
    const objectUrl = URL.createObjectURL(await response.blob());
    if (popup) popup.location.replace(objectUrl);
    else window.location.assign(objectUrl);
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch (error) {
    popup?.close();
    throw error;
  }
};
