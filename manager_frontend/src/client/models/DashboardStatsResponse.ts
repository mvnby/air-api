/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DashboardBankReceiptReviewItem } from './DashboardBankReceiptReviewItem';
import type { DashboardContractExpiry } from './DashboardContractExpiry';
import type { DashboardTouchpoint } from './DashboardTouchpoint';
export type DashboardStatsResponse = {
    total_amount: number;
    new_leads_count: number;
    upcoming_touchpoints: Array<DashboardTouchpoint>;
    expiring_contracts?: Array<DashboardContractExpiry>;
    bank_receipts_review_count?: number;
    bank_receipts_review?: Array<DashboardBankReceiptReviewItem>;
};

