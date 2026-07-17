/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotQuickOrderAddressCheck = {
    status: 'unchecked' | 'not_found' | 'needs_review' | 'confirmed';
    message: string;
    suggestion?: (string | null);
};

