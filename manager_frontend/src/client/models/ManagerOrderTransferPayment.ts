/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentCurrency } from './PaymentCurrency';
export type ManagerOrderTransferPayment = {
    source_id?: (number | null);
    amount: number;
    currency?: PaymentCurrency;
    date: string;
    type?: string;
    comment?: (string | null);
};

