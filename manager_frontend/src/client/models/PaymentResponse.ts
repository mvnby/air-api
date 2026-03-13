/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentCurrency } from './PaymentCurrency';
export type PaymentResponse = {
    id: number;
    amount: number;
    currency: PaymentCurrency;
    date: string;
    type: string;
    comment?: (string | null);
    created_at: string;
};

