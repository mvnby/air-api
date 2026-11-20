/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Consented first entry in the current visit, using only coarse categories.
 */
export type WebsiteArrival = {
    consent: boolean;
    landing_path: string;
    channel: 'organic_search' | 'paid' | 'referral' | 'campaign' | 'unknown';
    source?: ('google' | 'yandex' | 'bing' | 'duckduckgo' | 'chatgpt' | null);
};

