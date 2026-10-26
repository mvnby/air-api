import { computed, onScopeDispose, ref, watch, type Ref } from 'vue';
import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';
import type { ManagerOrderRequestContext, OrderRequestFile } from '../client';
import { serviceAttachmentsApi } from '../components/service-attachments/api';
import type { ServiceAttachmentItem, ServiceAttachmentAccessResponse } from '../components/service-attachments/types';
import { getApiErrorMessage } from '../utils/api-errors';

export function useOrderRequestContext(orderId: Readonly<Ref<number | undefined>>, active: Readonly<Ref<boolean>>) {
  const context = ref<Required<ManagerOrderRequestContext> | null>(null);
  const loading = ref(false), error = ref('');
  let revision = 0;
  const objectUrls = new Set<string>();
  const clearUrls = () => { for (const url of objectUrls) URL.revokeObjectURL(url); objectUrls.clear(); };
  const load = async () => {
    const id = orderId.value, version = ++revision;
    context.value = null; error.value = ''; loading.value = false;
    if (!id || !active.value) return;
    loading.value = true;
    try {
      const data = await request<Required<ManagerOrderRequestContext>>(OpenAPI, {
        method: 'GET', url: '/api/manager/orders/{order_id}/request-context', path: { order_id: id },
      });
      if (version === revision) context.value = data;
    } catch (reason) { if (version === revision) error.value = getApiErrorMessage(reason); }
    finally { if (version === revision) loading.value = false; }
  };
  const resolveAccess = async (item: ServiceAttachmentItem, download: boolean): Promise<ServiceAttachmentAccessResponse> => {
    const file = item as OrderRequestFile, version = revision;
    if (!file.available) throw new Error(file.processing_error || 'Оригинал недоступен.');
    if (!file.mail_attachment_id || !file.mail_message_id) {
      const access = await serviceAttachmentsApi.getAccess(file.id!, 'original', download);
      if (version !== revision) throw new Error('Заказ изменился.');
      return access;
    }
    const path = `/api/manager/mail/messages/${file.mail_message_id}/attachments/${file.mail_attachment_id}`;
    const options = { method: 'GET' as const, url: path };
    const token = typeof OpenAPI.TOKEN === 'function' ? await OpenAPI.TOKEN(options) : OpenAPI.TOKEN;
    const configured = typeof OpenAPI.HEADERS === 'function' ? await OpenAPI.HEADERS(options) : OpenAPI.HEADERS;
    const headers = new Headers(configured);
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const response = await fetch(`${OpenAPI.BASE}${path}`, { headers, credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin' });
    if (!response.ok) throw new Error(`Не удалось открыть оригинал (${response.status}). Повторите попытку.`);
    const blob = await response.blob();
    if (version !== revision) throw new Error('Заказ изменился.');
    const url = URL.createObjectURL(blob); objectUrls.add(url);
    return { url, variant: 'original', expires_at: '' };
  };
  watch([orderId, active], () => { clearUrls(); void load(); }, { immediate: true, flush: 'sync' });
  onScopeDispose(() => { revision++; clearUrls(); });
  const summary = computed(() => loading.value ? 'Проверяем файлы…' : error.value ? 'Файлы не загружены' : context.value ? `Файлов: ${context.value.files.length}` : 'Файлы не загружены');
  return { context, loading, error, load, summary, resolveAccess };
}
