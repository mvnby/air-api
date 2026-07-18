/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotTaskListRequest = {
    telegram_id: number;
    limit?: number;
    date_from?: (string | null);
    date_to?: (string | null);
    statuses?: Array<'planned' | 'in_progress' | 'completed' | 'canceled' | 'new_lead' | 'negotiation' | 'execution' | 'closed'>;
};

