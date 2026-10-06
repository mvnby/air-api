/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type IncomingResponse = {
    request_text: string;
    name?: (string | null);
    phone?: (string | null);
    email?: (string | null);
    region_text?: (string | null);
    address_text?: (string | null);
    requested_time_text?: (string | null);
    requested_at?: (string | null);
    lead_id: number;
    version: number;
    intake_state: 'needs_contact' | 'needs_details' | 'ready_for_review';
    missing_fields: Array<string>;
    source_occurred_at: (string | null);
    source_timezone: string;
    original_text: string;
    date_precision?: ('date' | 'datetime' | null);
    field_sources?: Record<string, string>;
    manager_url: string;
};

