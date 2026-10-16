import { OpenAPI, ManagerOrdersService, type ManagerOrderDetailResponse, type ManagerOrderResponsiblePerson, type ManagerOrderResponsibleUpdate } from '../client';
import { request } from '../client/core/request';

export type OrderResponsiblePerson = ManagerOrderResponsiblePerson;
export type OrderResponsibilityFields = Pick<ManagerOrderDetailResponse, 'responsible_person' | 'responsible_version'>;
export type OrderWithResponsibility = ManagerOrderDetailResponse;
export const orderResponsibilityApi = {
  candidates: (page = 1) => ManagerOrdersService.listManagerOrderResponsibles(page, 100),
  assign: (orderId: number, staffUserId: number | null, expectedVersion: number) => request<OrderWithResponsibility>(OpenAPI, {
    method: 'PATCH', url: `/api/manager/orders/${orderId}/responsible`, headers: { 'X-Kitlane-Team': '1' },
    body: { responsible_staff_user_id: staffUserId, expected_version: expectedVersion } satisfies ManagerOrderResponsibleUpdate, mediaType: 'application/json',
  }),
};
