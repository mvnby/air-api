/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaintenanceOfferCommand = {
    command_key: string;
    expected_version: number;
    action: 'issue' | 'send' | 'accept' | 'reject' | 'defer' | 'continue';
    source: string;
    comment: string;
    occurred_at: string;
    accepted_lines?: Array<string>;
};

