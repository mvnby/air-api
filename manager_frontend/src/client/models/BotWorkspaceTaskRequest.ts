/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotWorkspaceTaskRequest = {
    telegram_id: number;
    expected_context_version: number;
    expected_version: number;
    idempotency_key: string;
    action: 'complete' | 'reopen';
};

