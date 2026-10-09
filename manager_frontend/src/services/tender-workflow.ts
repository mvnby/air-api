import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';
import type { TenderWorkflowResponse } from '../client/models/TenderWorkflowResponse';
import type { TenderWorkflowIdentity } from '../client/models/TenderWorkflowIdentity';
import type { TenderWorkflowPayload } from '../client/models/TenderWorkflowPayload';
export type TenderWorkflow = TenderWorkflowResponse;
export type TenderIdentity = TenderWorkflowIdentity;
export type TenderStage = TenderWorkflowPayload['stage'];
export const tenderStageLabels: Record<TenderStage, string> = {
  price_request: 'Запрос цены', price_sent: 'Ценовое предложение отправлено',
  announced: 'Объявлена / готовим заявку', submitted: 'Заявка подана', completed: 'Завершена',
};
const base = '/api/manager/orders/{order_id}/tender-workflow';
export const tenderWorkflowApi = {
  get: (id: number) => request<TenderWorkflow>(OpenAPI, { method: 'GET', url: base, path: { order_id: id } }),
  update: (id: number, body: TenderWorkflowPayload) => request<TenderWorkflow>(OpenAPI, { method: 'PATCH', url: base, path: { order_id: id }, body, mediaType: 'application/json' }),
  candidates: (id: number, search: string) => request<TenderIdentity[]>(OpenAPI, { method: 'GET', url: `${base}/price-enquiries`, path: { order_id: id }, query: { search, limit: 20 } }),
  link: (id: number, priceId: number) => request<TenderWorkflow>(OpenAPI, { method: 'PUT', url: `${base}/price-enquiry`, path: { order_id: id }, body: { price_order_id: priceId }, mediaType: 'application/json' }),
  unlink: (id: number) => request<TenderWorkflow>(OpenAPI, { method: 'DELETE', url: `${base}/price-enquiry`, path: { order_id: id } }),
};
