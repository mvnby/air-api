import { OpenAPI, type NativeTemplateVersionItem } from '../../../client';

export async function downloadTemplateVersion(legalEntityId: number, version: NativeTemplateVersionItem) {
  const path = `/api/manager/document-system/templates/${version.template_id}/versions/${version.id}/source`;
  const token = typeof OpenAPI.TOKEN === 'function'
    ? await OpenAPI.TOKEN({ method: 'GET', url: path }) : OpenAPI.TOKEN;
  const response = await fetch(`${OpenAPI.BASE}${path}?legal_entity_id=${legalEntityId}`, {
    credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) throw new Error(`Не удалось скачать DOCX (${response.status})`);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = version.source_filename || `template-v${version.version}.docx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
