/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type IncomingOrderContext = {
    request_text: string;
    name?: (string | null);
    phone?: (string | null);
    email?: (string | null);
    region_text?: (string | null);
    workflow_type?: ('sales_installation' | 'service_work' | 'maintenance' | 'repair' | null);
    service_type?: ('turnkey' | 'install_only' | 'pre_install' | 'maintenance' | 'repair' | 'dismantling' | null);
    address_text?: (string | null);
    requested_time_text?: (string | null);
    requested_at?: (string | null);
    /**
     * Prior-call agreement, independent of a confirmed visit or task deadline.
     */
    call_before_visit?: (boolean | null);
    /**
     * Explicit instruction to save one linked clarification task. On creation, omission also recognizes standalone positive address/call instructions; false disables that text inference. MCP requires task-write scope when a task is requested.
     */
    clarification_requested?: (boolean | null);
    lead_id: number;
    lead_version: number;
    original_text: string;
    source_occurred_at?: (string | null);
    source_timezone: string;
    date_precision?: ('date' | 'datetime' | null);
    field_sources?: Record<string, string>;
    clarification_task_id?: (number | null);
    agreement_status?: string;
};

