/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WebRebuildStatusResponse = {
    current_revision: number;
    current_revision_updated_at: string;
    published_revision: number;
    published_at?: (string | null);
    requested_revision?: (number | null);
    requested_at?: (string | null);
    needs_rebuild: boolean;
    state: string;
    last_error?: (string | null);
};

