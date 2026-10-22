import { OpenAPI, type ManagerOrderBoardPage } from '../client';
import { request } from '../client/core/request';

export type OrderQueue = 'active' | 'waiting' | 'history';
export type BoardQuery = {
  segment: string; queue: OrderQueue | 'all'; status?: string; search?: string;
  assigned_to_me?: boolean; customer_id?: number; work_filter?: string;
  result?: string; closed_from?: string; closed_to?: string; include_unknown_date?: boolean;
  group_by_customer?: boolean; group_key?: string; column?: string; phase?: string;
  page?: number; limit?: number; sort?: string;
};
export const orderBoardApi = {
  page: (query: BoardQuery) => request<ManagerOrderBoardPage>(OpenAPI, {
    method: 'GET', url: '/api/manager/orders/board', query,
  }),
};
export const orderQueueLabel = (order: { status: string; is_on_hold?: boolean }) =>
  order.status === 'closed' ? 'История' : order.is_on_hold ? 'Ожидание' : 'Активные';
