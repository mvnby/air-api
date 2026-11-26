/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TenderMarketItem } from './TenderMarketItem';
export type TenderMarketResults = {
    items: Array<TenderMarketItem>;
    next_before_id?: (number | null);
    settings_version: number;
    profile_names: Array<string>;
    last_sync_at?: (string | null);
    syncing?: boolean;
};

