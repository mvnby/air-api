/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TenderLeadPushResult = {
    order_id: (number | null);
    outcome: 'created' | 'updated' | 'unchanged' | 'skipped';
    source: string;
    external_id: string;
};

