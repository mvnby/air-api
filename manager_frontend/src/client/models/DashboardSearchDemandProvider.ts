/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DashboardSearchDemandProvider = {
    last_attempt_at?: (string | null);
    next_retry_at?: (string | null);
    error_code?: (string | null);
    period_start?: (string | null);
    /**
     * Exclusive end of the actual saved source period; may precede the live CRM window.
     */
    period_end?: (string | null);
    provider: 'yandex_webmaster' | 'google_search_console';
    status: 'unconfigured' | 'pending' | 'fresh' | 'stale' | 'error';
    message?: (string | null);
    updated_at?: (string | null);
};

