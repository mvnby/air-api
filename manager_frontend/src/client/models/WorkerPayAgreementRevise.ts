/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkerPayAgreementRevise = {
    idempotency_key: string;
    expected_version: number;
    amount: (number | string);
    currency: 'BYN' | 'USD' | 'EUR';
    expected_agreement_version: number;
    cost_byn_amount?: (number | string | null);
};

