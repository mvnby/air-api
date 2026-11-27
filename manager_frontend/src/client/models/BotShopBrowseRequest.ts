/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotShopFilters } from './BotShopFilters';
export type BotShopBrowseRequest = {
    telegram_id: number;
    expected_context_version: number;
    filters?: BotShopFilters;
    page?: number;
    limit?: number;
    sort?: 'recommended' | 'retail_price' | 'title' | 'cooling_power' | 'availability';
    direction?: 'asc' | 'desc';
};

