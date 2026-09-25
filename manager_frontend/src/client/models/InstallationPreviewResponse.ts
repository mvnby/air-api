/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationAppliedDiscount } from './InstallationAppliedDiscount';
import type { InstallationComponent } from './InstallationComponent';
import type { InstallationSelectedWork } from './InstallationSelectedWork';
import type { InstallationWorkSummary } from './InstallationWorkSummary';
export type InstallationPreviewResponse = {
    status: 'fixed' | 'from' | 'quote' | 'unavailable';
    reason_code?: (string | null);
    scope_ref: string;
    currency?: string;
    components?: Array<InstallationComponent>;
    applied_discounts?: Array<InstallationAppliedDiscount>;
    installations?: Array<InstallationWorkSummary>;
    site_work?: Array<InstallationSelectedWork>;
    customer_text?: (string | null);
    subtotal?: (string | null);
    discount?: (string | null);
    total?: (string | null);
    price_book_id?: (number | null);
    price_book_revision?: (number | null);
    preview_ref?: (string | null);
    expires_at?: (string | null);
    explanation?: (string | null);
};

