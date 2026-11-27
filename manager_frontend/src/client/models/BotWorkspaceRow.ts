/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotWorkspaceRow = {
    id: number;
    kind: 'lead' | 'order' | 'customer' | 'task';
    title: string;
    subtitle?: (string | null);
    status?: (string | null);
    is_read?: (boolean | null);
};

