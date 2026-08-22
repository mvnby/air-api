/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DashboardKpi = {
    label: string;
    unit: 'byn' | 'count';
    current: number;
    /**
     * Previous-period value; null for current-state snapshots without historical state.
     */
    previous: (number | null);
    /**
     * Percentage change; null when the previous value is zero.
     */
    delta_pct?: (number | null);
    trend: 'up' | 'down' | 'flat' | 'unavailable';
};

