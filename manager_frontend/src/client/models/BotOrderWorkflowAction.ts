/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotOrderWorkflowAction = {
    action: 'negotiation:awaiting_offer' | 'negotiation:awaiting_visit' | 'negotiation:proposal_sent' | 'negotiation:awaiting_signature' | 'negotiation:awaiting_payment' | 'negotiation:follow_up' | 'execution:order_equipment' | 'execution:awaiting_equipment' | 'execution:needs_schedule' | 'execution:scheduled' | 'execution:work_done' | 'execution:awaiting_documents' | 'execution:awaiting_payment' | 'closed_won' | 'closed_lost' | 'wait' | 'resume';
    label: string;
    requires_confirmation?: boolean;
    requires_reason?: boolean;
    requires_reason_code?: boolean;
};

