/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentCurrency } from './PaymentCurrency';
export type BankReceiptResponse = {
    id: number;
    status: string;
    operation_type: string;
    sender_email: string;
    subject: string;
    message_id?: (string | null);
    fingerprint: string;
    email_date?: (string | null);
    received_at?: (string | null);
    our_account?: (string | null);
    amount: number;
    currency: PaymentCurrency;
    payer_name?: (string | null);
    payer_unp?: (string | null);
    payer_account?: (string | null);
    payment_document_raw?: (string | null);
    payment_document_number?: (string | null);
    payment_purpose?: (string | null);
    account_balance_after?: (number | null);
    parse_error?: (string | null);
    matched_order_id?: (number | null);
    matched_payment_id?: (number | null);
    match_meta?: (Record<string, any> | null);
    raw_body: string;
    created_at: string;
    updated_at?: (string | null);
};

