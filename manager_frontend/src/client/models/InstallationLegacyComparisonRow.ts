/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationLegacyCandidate } from './InstallationLegacyCandidate';
export type InstallationLegacyComparisonRow = {
    legacy_rate_id: number;
    legacy_category: string;
    legacy_power_range: string;
    legacy_base_price: string;
    legacy_route_extra_price: string;
    candidates?: Array<InstallationLegacyCandidate>;
    status: 'price_equal_review_required' | 'price_diff_review_required' | 'unmapped_review_required';
};

