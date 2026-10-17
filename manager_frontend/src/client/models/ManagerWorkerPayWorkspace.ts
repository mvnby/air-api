/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerWorkerPayAgreementItem } from './ManagerWorkerPayAgreementItem';
import type { WorkerPayBalance } from './WorkerPayBalance';
import type { WorkerPayEntry } from './WorkerPayEntry';
export type ManagerWorkerPayWorkspace = {
    worker_profile_id: (number | null);
    staff_user_id: number;
    display_name: string;
    version: number;
    can_manage: boolean;
    can_offset: boolean;
    balances: Array<WorkerPayBalance>;
    agreements: Array<ManagerWorkerPayAgreementItem>;
    items: Array<WorkerPayEntry>;
    total: number;
    page: number;
    limit: number;
};

