/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WebsiteLeadAttribution = {
    consent: boolean;
    landing_path: string;
    channel: 'organic_search' | 'paid' | 'referral' | 'campaign' | 'unknown';
    source?: ('google' | 'yandex' | 'bing' | 'duckduckgo' | 'chatgpt' | null);
    page_path: string;
    form_id: 'contact' | 'checkout' | 'installation_calculator' | 'installation_estimate' | 'repair_diagnostic' | 'product_availability' | 'multi_split';
};

