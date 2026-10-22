import { OpenAPI, type ManagerOrderDetailResponse, type ManagerOrderWaitingCommand } from '../client';
import { request } from '../client/core/request';
export const WAITING_REASONS = [
  { value: 'next_stage', label: 'Следующий этап работ' },
  { value: 'site_readiness', label: 'Готовность объекта' },
  { value: 'customer_decision', label: 'Решение клиента' },
  { value: 'other', label: 'Другое' },
] as const;
export const waitingReasonLabel = (code?: string | null) => WAITING_REASONS.find(reason => reason.value === code)?.label || 'Другое';
export const orderWaitingApi = {
  command: (orderId: number, body: ManagerOrderWaitingCommand) => request<ManagerOrderDetailResponse>(OpenAPI, {
    method: 'POST', url: `/api/manager/orders/${orderId}/waiting`, body, mediaType: 'application/json',
  }),
};

export const waitingDescription = (order: { on_hold_reason_code?: string | null; on_hold_reason?: string | null; on_hold_started_at?: string | null; next_followup_date?: string | null }) => {
  const parts = [order.on_hold_reason_code ? waitingReasonLabel(order.on_hold_reason_code) : '', order.on_hold_reason].filter(Boolean);
  if (order.on_hold_started_at) parts.push(`С ${new Date(order.on_hold_started_at).toLocaleDateString('ru-RU')}`);
  parts.push(order.next_followup_date ? `Контакт ${new Date(order.next_followup_date).toLocaleString('ru-RU')}` : 'Без срока контакта');
  return parts.join(' · ');
};
