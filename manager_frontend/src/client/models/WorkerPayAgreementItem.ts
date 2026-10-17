/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkerPayAgreementItem = {
    id: number;
    worker_profile_id: number;
    order_id: number;
    assignment_reference: number;
    work_stage_id: (number | null);
    work_key: string;
    title: string;
    amount: string;
    currency: string;
    status: 'agreed' | 'accrued' | 'cancelled';
    version: number;
    paid: string;
    owed: string;
    created_at: string;
};

