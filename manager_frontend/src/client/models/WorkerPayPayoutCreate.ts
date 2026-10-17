/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkerPayPayoutCreate = {
    idempotency_key: string;
    expected_version: number;
    amount: (number | string);
    currency: 'BYN' | 'USD' | 'EUR';
    method?: 'cash' | 'bank';
};

