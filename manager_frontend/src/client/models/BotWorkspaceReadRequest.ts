/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotWorkspaceReadRequest = {
    telegram_id: number;
    expected_context_version: number;
    kind: 'lead' | 'order';
    is_read: boolean;
};

