/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotOrderTransition = {
    kind: string;
    action: 'negotiation:awaiting_offer' | 'negotiation:awaiting_visit' | 'negotiation:proposal_sent' | 'negotiation:awaiting_signature' | 'negotiation:awaiting_payment' | 'negotiation:follow_up' | 'execution:order_equipment' | 'execution:awaiting_equipment' | 'execution:needs_schedule' | 'execution:scheduled' | 'execution:work_done' | 'execution:awaiting_documents' | 'execution:awaiting_payment' | 'closed_won' | 'closed_lost' | 'wait' | 'resume';
    confirmed?: boolean;
    reason?: (string | null);
    reason_code?: ('next_stage' | 'site_readiness' | 'customer_decision' | 'other' | null);
};

