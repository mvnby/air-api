/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TypedInstallationProfile_Output } from './TypedInstallationProfile_Output';
export type InstallationResolveResponse = {
    status: 'fixed' | 'from' | 'provisional' | 'quote' | 'unavailable';
    reason_code?: (string | null);
    profile?: (TypedInstallationProfile_Output | null);
    profile_sources?: Record<string, string>;
    matched_by?: Array<string>;
    tariff_code?: (string | null);
    scope_ref: string;
    price_book_id?: (number | null);
    price_book_revision?: (number | null);
    included?: Record<string, any>;
    available_extras?: Array<string>;
    explanation?: (string | null);
    price_mode?: ('fixed' | 'from' | 'quote' | null);
    base_price?: (string | null);
};

