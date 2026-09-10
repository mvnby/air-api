/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderUsageDailyItem } from './OrderUsageDailyItem';
export type OrderUsageReport = {
    days: number;
    since: string;
    through: string;
    timezone?: string;
    layout_version?: string;
    items: Array<OrderUsageDailyItem>;
};

