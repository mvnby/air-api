/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type InboxArchivePayload = {
    outcome: 'refusal' | 'spam' | 'duplicate';
    reason?: ('profile' | 'region' | 'terms' | 'capacity' | 'unclear' | 'other' | null);
    note?: (string | null);
};

