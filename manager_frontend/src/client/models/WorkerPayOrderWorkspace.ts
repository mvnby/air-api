/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerWorkerPayAgreementItem } from './ManagerWorkerPayAgreementItem';
import type { WorkerPayCandidate } from './WorkerPayCandidate';
export type WorkerPayOrderWorkspace = {
    order_id: number;
    candidates: Array<WorkerPayCandidate>;
    agreements: Array<ManagerWorkerPayAgreementItem>;
    can_manage: boolean;
};

