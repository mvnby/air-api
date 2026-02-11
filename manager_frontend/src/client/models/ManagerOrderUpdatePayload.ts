/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderProductLinePayload } from './ManagerOrderProductLinePayload';
import type { ManagerOrderServiceLinePayload } from './ManagerOrderServiceLinePayload';
export type ManagerOrderUpdatePayload = {
    status?: (string | null);
    next_followup_date?: (string | null);
    assessment_date?: (string | null);
    installation_date?: (string | null);
    comment?: (string | null);
    is_paid?: (boolean | null);
    products?: (Array<ManagerOrderProductLinePayload> | null);
    services?: (Array<ManagerOrderServiceLinePayload> | null);
};

