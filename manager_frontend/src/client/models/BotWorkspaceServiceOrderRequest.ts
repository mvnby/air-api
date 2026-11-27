/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotWorkspaceServiceOrderRequest = {
    telegram_id: number;
    expected_context_version: number;
    expected_version: number;
    idempotency_key: string;
    kind: 'lead' | 'order';
    customer_id: number;
    workflow_type: 'repair' | 'service_work' | 'maintenance';
};

