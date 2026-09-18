/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogUsageDailyItem } from './CatalogUsageDailyItem';
export type CatalogUsageReport = {
    days: number;
    since: string;
    through: string;
    timezone?: string;
    items: Array<CatalogUsageDailyItem>;
};

