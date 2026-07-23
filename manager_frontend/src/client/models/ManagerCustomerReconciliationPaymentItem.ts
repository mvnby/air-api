/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentCurrency } from './PaymentCurrency';
export type ManagerCustomerReconciliationPaymentItem = {
    payment_id: number;
    order_id: number;
    order_title: string;
    date: string;
    amount: number;
    allocated_amount?: (number | null);
    currency: PaymentCurrency;
    payment_type: string;
    comment?: (string | null);
    bank_receipt_id?: (number | null);
    payer_name?: (string | null);
    payer_unp?: (string | null);
    payer_account?: (string | null);
    our_account?: (string | null);
    payment_document_number?: (string | null);
    payment_document_raw?: (string | null);
    payment_purpose?: (string | null);
};

