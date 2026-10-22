/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DashboardMarketingProvider = {
    last_attempt_at?: (string | null);
    next_retry_at?: (string | null);
    error_code?: (string | null);
    period_start?: (string | null);
    /**
     * Exclusive end of the actual saved source period; may precede the live CRM window.
     */
    period_end?: (string | null);
    provider: 'yandex_metrika' | 'yandex_direct' | 'google_analytics' | 'google_ads';
    status: 'unconfigured' | 'pending' | 'fresh' | 'stale' | 'error';
    visits?: (number | null);
    sessions?: (number | null);
    active_users?: (number | null);
    bounce_rate?: (number | null);
    engagement_rate?: (number | null);
    average_session_duration_seconds?: (number | null);
    ad_spend?: (number | null);
    clicks?: (number | null);
    impressions?: (number | null);
    ctr?: (number | null);
    platform_conversions?: (number | null);
    currency?: (string | null);
    message?: (string | null);
    updated_at?: (string | null);
};

