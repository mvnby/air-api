/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WorkerCashBalance } from './WorkerCashBalance';
import type { WorkerMoneyEntry } from './WorkerMoneyEntry';
export type WorkerMoneyWorkspace = {
    worker_profile_id: (number | null);
    staff_user_id: number;
    display_name: string;
    version: number;
    can_manage: boolean;
    balances: Array<WorkerCashBalance>;
    items: Array<WorkerMoneyEntry>;
    total: number;
    page: number;
    limit: number;
};

