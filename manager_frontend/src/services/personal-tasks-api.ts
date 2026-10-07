import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';

export type PersonalTaskStatus = 'active' | 'completed' | 'cancelled';
export type PersonalTaskFilter = PersonalTaskStatus | 'today' | 'overdue' | 'undated';

export type PersonalTask = {
  id: number;
  text: string;
  description?: string | null;
  status: PersonalTaskStatus;
  version: number;
  author_staff_user_id: number;
  author_name: string;
  assignee_staff_user_id?: number | null;
  assignee_name?: string | null;
  due_at?: string | null;
  reminder_at?: string | null;
  reminder_due: boolean;
  lead_id?: number | null;
  customer_id?: number | null;
  order_id?: number | null;
  equipment_id?: number | null;
  completed_at?: string | null;
  cancelled_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type PersonalTaskList = {
  items: PersonalTask[];
  total: number;
  limit: number;
  offset: number;
  filter: PersonalTaskFilter;
  due_reminder_count: number;
};

export type PersonalTaskAssignee = {
  id: number;
  display_name: string;
};

export type PersonalTaskCreate = {
  text: string;
  description?: string | null;
  assignee_staff_user_id?: number | null;
  due_at?: string | null;
  reminder_at?: string | null;
  lead_id?: number | null;
  customer_id?: number | null;
  order_id?: number | null;
  equipment_id?: number | null;
};

export type PersonalTaskUpdate = Partial<PersonalTaskCreate> & {
  expected_version: number;
};

export const newPersonalTaskCommandKey = (): string => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `task-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const base = '/api/manager/personal-tasks';

export const getPersonalTask = (taskId: number): Promise<PersonalTask> => request(OpenAPI, {
  method: 'GET', url: `${base}/${taskId}`,
});

export const listPersonalTasks = (
  filter: PersonalTaskFilter,
  limit = 100,
  offset = 0,
): Promise<PersonalTaskList> => request<PersonalTaskList>(OpenAPI, {
  method: 'GET', url: base, query: { filter, limit, offset },
});

export const listPersonalTaskAssignees = (): Promise<{ items: PersonalTaskAssignee[] }> => request(OpenAPI, {
  method: 'GET', url: `${base}/assignees`, query: { limit: 100 },
});

export const createPersonalTask = (payload: PersonalTaskCreate, commandKey: string): Promise<PersonalTask> => request(OpenAPI, {
  method: 'POST', url: base, body: payload, mediaType: 'application/json', headers: { 'Idempotency-Key': commandKey },
});

export const updatePersonalTask = (taskId: number, payload: PersonalTaskUpdate, commandKey: string): Promise<PersonalTask> => request(OpenAPI, {
  method: 'PATCH', url: `${base}/${taskId}`, body: payload, mediaType: 'application/json', headers: { 'Idempotency-Key': commandKey },
});

export const changePersonalTaskStatus = (
  taskId: number,
  action: 'complete' | 'reopen' | 'cancel',
  expectedVersion: number,
  commandKey: string,
): Promise<PersonalTask> => request(OpenAPI, {
  method: 'POST', url: `${base}/${taskId}/${action}`, body: { expected_version: expectedVersion },
  mediaType: 'application/json', headers: { 'Idempotency-Key': commandKey },
});
