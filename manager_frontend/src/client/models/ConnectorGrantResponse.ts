/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ConnectorGrantResponse = {
    id: number;
    client_id: string;
    tenant_id: number;
    storefront_id: number;
    scopes: Array<string>;
    created_at: string;
    expires_at: string;
    revoked_at: (string | null);
};

