import { OpenAPI, type MailAccountResponse, type MailAttachmentResponse, type MailMessageResponse, type MailDraftCreatePayload, type MailOrderDraftPayload, type IncomingMailSyncResponse } from '../client';
import { request } from '../client/core/request';

export type MailFolder = MailMessageResponse['folder'];
// The server serializes Pydantic defaults. Keep their generated definitions as the source of truth.
export type MailAccount = Required<MailAccountResponse>;
export type MailAttachment = Required<MailAttachmentResponse>;
export type MailMessage = Omit<MailMessageResponse, 'attachments'> & Required<Pick<MailMessageResponse, 'to' | 'cc' | 'bcc' | 'subject' | 'body_text' | 'order_id' | 'customer_id'>> & { attachments: MailAttachment[] };
export type MailDraftFields = MailDraftCreatePayload;
export type MailListFilters = { folder: MailFolder; page: number; limit: number; q?: string; status?: string; order_id?: number };
export const mailCommandKey = () => crypto.randomUUID();

export const mailApi = {
  sync(): Promise<IncomingMailSyncResponse> {
    return request(OpenAPI, { method: 'POST', url: '/api/manager/mail/sync', body: { limit: 50 }, mediaType: 'application/json', headers: { 'Idempotency-Key': mailCommandKey() } });
  },
  accounts(): Promise<{ items: MailAccount[] }> {
    return request(OpenAPI, { method: 'GET', url: '/api/manager/mail/accounts' });
  },
  list(filters: MailListFilters): Promise<{ items: MailMessage[]; total: number; page: number; limit: number }> {
    return request(OpenAPI, { method: 'GET', url: '/api/manager/mail/messages', query: filters });
  },
  get(id: number): Promise<MailMessage> {
    return request(OpenAPI, { method: 'GET', url: '/api/manager/mail/messages/{id}', path: { id } });
  },
  create(fields: MailDraftFields, key = mailCommandKey()): Promise<MailMessage> {
    return request(OpenAPI, { method: 'POST', url: '/api/manager/mail/drafts', body: fields, mediaType: 'application/json', headers: { 'Idempotency-Key': key } });
  },
  createOrderDraft(orderId: number, fields: MailOrderDraftPayload, transport: 'legacy' | 'native'): Promise<MailMessage> {
    return request(OpenAPI, { method: 'POST', url: transport === 'native' ? '/api/manager/document-system/orders/{order_id}/email/draft' : '/api/manager/mail/orders/{order_id}/draft', path: { order_id: orderId }, body: fields, mediaType: 'application/json', headers: { 'Idempotency-Key': mailCommandKey() } });
  },
  copy(id: number, expectedVersion: number): Promise<MailMessage> {
    return request(OpenAPI, { method: 'POST', url: '/api/manager/mail/messages/{id}/copy', path: { id }, body: { expected_version: expectedVersion }, mediaType: 'application/json', headers: { 'Idempotency-Key': mailCommandKey() } });
  },
  update(id: number, expectedVersion: number, fields: MailDraftFields, key = mailCommandKey()): Promise<MailMessage> {
    return request(OpenAPI, { method: 'PATCH', url: '/api/manager/mail/drafts/{id}', path: { id }, body: { ...fields, expected_version: expectedVersion }, mediaType: 'application/json', headers: { 'Idempotency-Key': key } });
  },
  remove(id: number, expectedVersion: number): Promise<void> {
    return request(OpenAPI, { method: 'DELETE', url: '/api/manager/mail/drafts/{id}', path: { id }, body: { expected_version: expectedVersion }, mediaType: 'application/json', headers: { 'Idempotency-Key': mailCommandKey() } });
  },
  upload(id: number, expectedVersion: number, file: File): Promise<MailMessage> {
    return request(OpenAPI, { method: 'POST', url: '/api/manager/mail/drafts/{id}/attachments', path: { id }, formData: { expected_version: expectedVersion, file }, headers: { 'Idempotency-Key': mailCommandKey() } });
  },
  removeAttachment(id: number, attachmentId: number, expectedVersion: number): Promise<MailMessage> {
    return request(OpenAPI, { method: 'DELETE', url: '/api/manager/mail/drafts/{id}/attachments/{attachment_id}', path: { id, attachment_id: attachmentId }, query: { expected_version: expectedVersion }, headers: { 'Idempotency-Key': mailCommandKey() } });
  },
  preview(id: number): Promise<MailMessage> {
    return request(OpenAPI, { method: 'GET', url: '/api/manager/mail/drafts/{id}/preview', path: { id } });
  },
  confirm(id: number, expectedVersion: number, contentHash: string, csrfToken: string): Promise<MailMessage> {
    return request(OpenAPI, { method: 'POST', url: '/api/manager/mail/drafts/{id}/confirm', path: { id }, body: { expected_version: expectedVersion, content_hash: contentHash }, mediaType: 'application/json', headers: { 'Idempotency-Key': mailCommandKey(), 'X-Kitlane-Mail-Approval': 'manager-review', 'X-CSRF-Token': csrfToken } });
  },
  send(id: number, expectedVersion: number, key: string, csrfToken: string): Promise<MailMessage> {
    return request(OpenAPI, { method: 'POST', url: '/api/manager/mail/drafts/{id}/send', path: { id }, body: { expected_version: expectedVersion }, mediaType: 'application/json', headers: { 'Idempotency-Key': key, 'X-Kitlane-Mail-Approval': 'manager-review', 'X-CSRF-Token': csrfToken } });
  },
};

export const mailStatusLabel = (status: string) => ({ draft: 'Черновик', pending: 'Ожидает отправки', sending: 'Отправляется', sent: 'Принято почтовым сервером', failed: 'Ошибка отправки', unknown: 'Результат требует проверки', received: 'Получено' }[status] || status);

export async function downloadMailAttachment(attachment: MailAttachment) {
  if (!attachment.available || !attachment.download_url) throw new Error('Файл не сохранён. Повторить отправку с этим вложением нельзя.');
  // Never send credentials to an URL supplied by message content.
  const configuredBase = new URL(OpenAPI.BASE || window.location.origin, window.location.origin);
  const url = new URL(attachment.download_url, configuredBase);
  if (url.origin !== configuredBase.origin || !url.pathname.startsWith('/api/manager/mail/')) throw new Error('Недоступная ссылка на вложение');
  const token = typeof OpenAPI.TOKEN === 'function' ? await OpenAPI.TOKEN({ method: 'GET', url: url.pathname }) : OpenAPI.TOKEN;
  const response = await fetch(url.href, { credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin', headers: token ? { Authorization: `Bearer ${token}` } : undefined });
  if (!response.ok) throw new Error(`Не удалось скачать файл (${response.status})`);
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = attachment.filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}
