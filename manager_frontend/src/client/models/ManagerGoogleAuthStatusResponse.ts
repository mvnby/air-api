/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerGoogleAuthStatusResponse = {
    exists: boolean;
    valid: boolean;
    expired: boolean;
    expiry?: (string | null);
    scopes?: Array<string>;
    persistence_ok: boolean;
    persistence_error_code?: (string | null);
};

