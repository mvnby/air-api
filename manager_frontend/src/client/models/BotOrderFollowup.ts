/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotOrderFollowupCustomer } from './BotOrderFollowupCustomer';
import type { BotOrderWorkflowAction } from './BotOrderWorkflowAction';
export type BotOrderFollowup = {
    status: 'new_lead' | 'negotiation' | 'execution' | 'closed';
    closing_result?: ('won' | 'lost' | null);
    reject_reason?: (string | null);
    customer?: (BotOrderFollowupCustomer | null);
    contact_name?: (string | null);
    contact_phone?: (string | null);
    delivery_address?: (string | null);
    comment?: (string | null);
    measurement_required?: boolean;
    measurement_date?: (string | null);
    installation_date?: (string | null);
    next_followup_date?: (string | null);
    negotiation_status?: (string | null);
    execution_status?: (string | null);
    workflow_status_label?: (string | null);
    is_on_hold?: boolean;
    on_hold_reason_code?: (string | null);
    on_hold_reason?: (string | null);
    can_edit_details?: boolean;
    can_assign_customer?: boolean;
    can_create_customer?: boolean;
    customer_assignment_requires_confirmation?: boolean;
    schedule_fields?: Array<'measurement_date' | 'installation_date' | 'next_followup_date'>;
    workflow_actions?: Array<BotOrderWorkflowAction>;
};

