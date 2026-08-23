/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DashboardMarketingProvider = {
    provider: 'yandex_metrika' | 'yandex_direct' | 'google_analytics' | 'google_ads';
    status: 'unconfigured' | 'fresh' | 'stale' | 'error';
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
};

