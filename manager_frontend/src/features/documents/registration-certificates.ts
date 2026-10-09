import { OpenAPI } from '../../client';
export type RegistrationCertificate = { id: string; legal_entity_id: number; filename: string; mime_type: string; checksum_sha256: string; size_bytes: number; is_current: boolean; created_at: string };
export async function certificateRequest(path: string, method = 'GET', body?: FormData): Promise<Response> {
  const token = typeof OpenAPI.TOKEN === 'function' ? await OpenAPI.TOKEN({ method: method as 'GET', url: path }) : OpenAPI.TOKEN;
  const response = await fetch(`${OpenAPI.BASE}${path}`, { method, body, headers: token ? { Authorization: `Bearer ${token}` } : undefined, credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin' });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail?.message || payload?.detail || 'Не удалось загрузить свидетельство');
  }
  return response;
}
export async function listCertificates(entityId: number): Promise<RegistrationCertificate[]> {
  return (await certificateRequest(`/api/manager/document-system/legal-entities/${entityId}/registration-certificates`)).json();
}
export async function downloadCertificate(item: RegistrationCertificate) {
  const response = await certificateRequest(`/api/manager/document-system/registration-certificates/${item.id}/download`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href = url; link.download = item.filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
