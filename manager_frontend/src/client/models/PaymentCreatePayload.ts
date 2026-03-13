/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentCurrency } from './PaymentCurrency';
export type PaymentCreatePayload = {
    amount: number;
    currency?: PaymentCurrency;
    type: string;
    comment?: (string | null);
};

