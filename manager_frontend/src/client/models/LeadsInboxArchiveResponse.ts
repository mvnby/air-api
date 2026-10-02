/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LeadsInboxArchiveResponse = {
    outcome: 'refusal' | 'spam' | 'duplicate' | 'deadline_expired' | 'legacy_lost' | 'linked';
    reason?: (string | null);
    note?: (string | null);
    archived_at?: (string | null);
    actor?: (string | null);
};

