/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PersonalTaskResponse } from './PersonalTaskResponse';
export type PersonalTaskListResponse = {
    items: Array<PersonalTaskResponse>;
    total: number;
    limit: number;
    offset: number;
    filter: 'active' | 'today' | 'overdue' | 'undated' | 'completed' | 'cancelled';
    due_reminder_count: number;
};

