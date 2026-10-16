/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerCollectionInstruction = {
    version: number;
    assignment_id: (number | null);
    amount: (string | null);
    currency: ('BYN' | 'USD' | 'EUR' | null);
    status: 'not_assigned' | 'ready' | 'requires_review';
    updated_at: (string | null);
};

