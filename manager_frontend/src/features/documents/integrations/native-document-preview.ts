import { OpenAPI } from '../../../client';
import type { ApiRequestOptions } from '../../../client/core/ApiRequestOptions';

const resolveToken = async (method: ApiRequestOptions['method'], url: string) => {
  if (typeof OpenAPI.TOKEN === 'function') return OpenAPI.TOKEN({ method, url });
  return OpenAPI.TOKEN;
};

const fetchPreview = async (documentId: number, query = '') => {
  const path = `/api/manager/document-system/documents/${encodeURIComponent(String(documentId))}/preview`;
  const token = await resolveToken('GET', path);
  const response = await fetch(`${OpenAPI.BASE}${path}${query}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail?.message || payload?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Ошибка запроса (${response.status})`);
  }
  return response;
};

export const fetchDraftPreviewWithPage = async (documentId: number) => {
  const response = await fetchPreview(documentId, '?include_first_page=true');
  if (response.headers.get('Content-Type')?.startsWith('multipart/form-data')) {
    const files = await response.formData();
    const pdf = files.get('pdf');
    const firstPage = files.get('first_page');
    if (pdf instanceof Blob && pdf.type === 'application/pdf') {
      return { pdf, firstPage: firstPage instanceof Blob && firstPage.type === 'image/png' ? firstPage : null };
    }
    throw new Error('В предпросмотре отсутствует файл PDF.');
  }
  return { pdf: await response.blob(), firstPage: null };
};

export const openNativeDocumentPreview = async (documentId: number) => {
  const popup = window.open('about:blank', '_blank');
  if (popup) popup.opener = null;
  try {
    const objectUrl = URL.createObjectURL(await (await fetchPreview(documentId)).blob());
    if (popup) popup.location.replace(objectUrl);
    else window.location.assign(objectUrl);
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
  } catch (error) {
    popup?.close();
    throw error;
  }
};
