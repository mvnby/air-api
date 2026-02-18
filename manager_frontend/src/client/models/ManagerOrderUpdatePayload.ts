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
    customer_name?: (string | null);
    customer_phone?: (string | null);
    customer_email?: (string | null);
    customer_inn?: (string | null);
    customer_full_legal_name?: (string | null);
    customer_legal_address?: (string | null);
    customer_bank_name?: (string | null);
    customer_bic?: (string | null);
    customer_iban?: (string | null);
    customer_delivery_address?: (string | null);
    confirm_critical_customer_changes?: (boolean | null);
    products?: (Array<ManagerOrderProductLinePayload> | null);
    services?: (Array<ManagerOrderServiceLinePayload> | null);
};

