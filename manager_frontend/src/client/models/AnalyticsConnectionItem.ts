/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AnalyticsConnectionItem = {
    provider: 'yandex_metrika' | 'yandex_direct' | 'yandex_webmaster' | 'google_analytics' | 'google_ads' | 'google_search_console';
    label: string;
    description: string;
    state: 'connected' | 'not_configured' | 'coming_soon' | 'error';
    available: boolean;
    credentials_configured?: boolean;
    counter_id?: (string | null);
    counter_name?: (string | null);
    site?: (string | null);
    last_verified_at?: (string | null);
    last_error_code?: (string | null);
    configuration?: Record<string, string>;
};

