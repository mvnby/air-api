/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmailLeadDecisionResponse } from './EmailLeadDecisionResponse';
export type EmailLeadImportResponse = {
    processed?: number;
    scanned_since?: (string | null);
    last_import_at?: (string | null);
    candidates?: number;
    ai_checked?: number;
    would_create?: number;
    created?: number;
    duplicates?: number;
    rejected?: number;
    failed?: number;
    lead_ids?: Array<number>;
    created_lead_ids?: Array<number>;
    order_ids?: Array<number>;
    created_order_ids?: Array<number>;
    decisions?: Array<EmailLeadDecisionResponse>;
};

