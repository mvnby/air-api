/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DashboardSearchQuery = {
    provider: 'yandex_webmaster' | 'google_search_console';
    query: string;
    clicks: number;
    impressions: number;
    ctr: number;
    avg_position?: (number | null);
};

