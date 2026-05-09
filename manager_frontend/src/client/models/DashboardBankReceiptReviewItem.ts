/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentCurrency } from './PaymentCurrency';
export type DashboardBankReceiptReviewItem = {
    id: number;
    received_at?: (string | null);
    amount: number;
    currency: PaymentCurrency;
    payer_name?: (string | null);
    payer_unp?: (string | null);
    payment_document_number?: (string | null);
    payment_purpose?: (string | null);
    candidate_order_ids?: Array<number>;
};

