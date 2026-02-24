/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderProductLinePayload } from './ManagerOrderProductLinePayload';
import type { ManagerOrderServiceLinePayload } from './ManagerOrderServiceLinePayload';
export type ManagerOrderUpdatePayload = {
    status?: (string | null);
    next_followup_date?: (string | null);
    measurement_date?: (string | null);
    installation_date?: (string | null);
    comment?: (string | null);
    no_answer_at?: (string | null);
    measurement_required?: (boolean | null);
    measurer_id?: (number | null);
    measurement_result?: (string | null);
    proposal_status?: (string | null);
    is_paid?: (boolean | null);
    closing_result?: (string | null);
    reject_reason?: (string | null);
    is_on_hold?: (boolean | null);
    on_hold_reason?: (string | null);
    proposal_sent_at?: (string | null);
    customer_id?: (number | null);
    customer_type?: (string | null);
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
    object_type?: (string | null);
    service_type?: (string | null);
    equipment_class?: (string | null);
    marketing_source?: (string | null);
    installer_id?: (number | null);
    products?: (Array<ManagerOrderProductLinePayload> | null);
    services?: (Array<ManagerOrderServiceLinePayload> | null);
};

