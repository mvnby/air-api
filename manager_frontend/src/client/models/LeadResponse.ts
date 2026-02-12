/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LeadResponse = {
    id: number;
    status: string;
    source: string;
    segment_hint: string;
    name?: (string | null);
    phone?: (string | null);
    email?: (string | null);
    inn?: (string | null);
    company_name?: (string | null);
    request_text: string;
    loss_reason?: (string | null);
    next_followup_date?: (string | null);
    archived_at?: (string | null);
    converted_order_id?: (number | null);
    created_at: string;
    updated_at?: (string | null);
};

