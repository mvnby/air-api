/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentCurrency } from './PaymentCurrency';
export type PaymentBankReceiptResponse = {
    id: number;
    status: string;
    received_at?: (string | null);
    amount: number;
    currency: PaymentCurrency;
    payer_name?: (string | null);
    payer_unp?: (string | null);
    payer_account?: (string | null);
    payment_document_raw?: (string | null);
    payment_document_number?: (string | null);
    payment_purpose?: (string | null);
};

