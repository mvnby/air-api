/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationMatcher_Output } from './InstallationMatcher_Output';
export type InstallationLegacyCandidate = {
    tariff_code: string;
    matcher: InstallationMatcher_Output;
    mode: 'fixed' | 'from' | 'quote';
    base_price: string;
    route_extra_price?: (string | null);
};

