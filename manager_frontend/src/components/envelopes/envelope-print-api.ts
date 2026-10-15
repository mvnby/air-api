import { OpenAPI, type EnvelopePrintPayload } from '../../client';

export async function downloadEnvelope(customerId: number, payload: EnvelopePrintPayload): Promise<Blob> {
  const path = `/api/manager/customers/${customerId}/envelope-pdf`;
  const token = typeof OpenAPI.TOKEN === 'function'
    ? await OpenAPI.TOKEN({ method: 'POST', url: path }) : OpenAPI.TOKEN;
  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    method: 'POST',
    credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'application/pdf', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(typeof error?.detail?.message === 'string' ? error.detail.message : 'Не удалось сформировать конверт. Проверьте адресные данные.');
  }
  return response.blob();
}
