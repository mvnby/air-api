/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotOrderPayment } from './BotOrderPayment';
export type BotOrderPayments = {
    total_amount: string;
    total_payments: string;
    balance_due: string;
    entries?: Array<BotOrderPayment>;
    currencies?: Array<'BYN' | 'USD' | 'EUR'>;
    target_currency?: ('USD' | 'EUR' | null);
    target_currency_amount?: (string | null);
    target_currency_payments?: (string | null);
    target_currency_balance_due?: (string | null);
    exchange_rate?: (string | null);
    received_on_max: string;
    can_record?: boolean;
    record_unavailable_reason?: (string | null);
    workflow_notice?: (string | null);
};

