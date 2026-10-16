import { OpenAPI, type WorkerPerson, type ManagerInstallerWorkspace, type ManagerWorkerAssignment, type WorkerAssignmentPublicationUpdate, type ManagerCollectionUpdate } from '../client';
import { request } from '../client/core/request';
export type { WorkerPerson, ManagerInstallerWorkspace } from '../client';
export type WorkerAssignment = ManagerWorkerAssignment;
export type WorkerPublication = WorkerAssignmentPublicationUpdate;
export type CollectionUpdate = ManagerCollectionUpdate;
const base = (orderId: number) => `/api/manager/orders/${orderId}/installer-workspace`;
const mutation = (method: 'POST' | 'PATCH' | 'PUT', url: string, body: unknown) => request<ManagerInstallerWorkspace>(OpenAPI, { method, url, headers: { 'X-Kitlane-Team': '1' }, body, mediaType: 'application/json' });
export const orderWorkerAssignmentsApi = {
  get: (orderId: number) => request<ManagerInstallerWorkspace>(OpenAPI, { method: 'GET', url: base(orderId) }),
  candidates: (page = 1) => request<{ items: WorkerPerson[]; total: number; page: number; limit: number }>(OpenAPI, { method: 'GET', url: '/api/manager/worker-candidates', query: { page, limit: 100 } }),
  assign: (orderId: number, staff_user_id: number, work_stage_id: number | null) => mutation('POST', `${base(orderId)}/assignments`, { staff_user_id, work_stage_id }),
  publish: (orderId: number, id: number, body: WorkerPublication) => mutation('PATCH', `${base(orderId)}/assignments/${id}`, body),
  revoke: (orderId: number, id: number, expected_version: number) => mutation('POST', `${base(orderId)}/assignments/${id}/revoke`, { expected_version }),
  collection: (orderId: number, body: CollectionUpdate) => mutation('PUT', `${base(orderId)}/collection`, body),
};
