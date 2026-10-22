/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerOrderWaitingCommand = {
    action: 'wait' | 'resume';
    expected_revision: number;
    reason_code?: ('next_stage' | 'site_readiness' | 'customer_decision' | 'other' | null);
    note?: (string | null);
    next_followup_date?: (string | null);
};

