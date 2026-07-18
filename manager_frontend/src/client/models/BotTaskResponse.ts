/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Stable read-only task projection rendered by the Telegram runtime.
 */
export type BotTaskResponse = {
    kind: 'stage' | 'order';
    id: number;
    order_id: number;
    stage_id?: (number | null);
    title: string;
    status: string;
    start_time: string;
    address?: (string | null);
    customer_name?: string;
    customer_phone?: (string | null);
    comment?: (string | null);
    manager_url?: (string | null);
};

