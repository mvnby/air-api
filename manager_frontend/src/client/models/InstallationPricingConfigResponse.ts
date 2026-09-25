/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationPricingCapabilities } from './InstallationPricingCapabilities';
export type InstallationPricingConfigResponse = {
    source: 'legacy' | 'price_book';
    price_book_revision?: (number | null);
    scope_ref: string;
    service_enabled: boolean;
    capabilities: InstallationPricingCapabilities;
};

