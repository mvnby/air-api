/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderSiteItem } from './OrderSiteItem';
import type { OrderSiteLegacyPrimary } from './OrderSiteLegacyPrimary';
export type OrderSiteList = {
    items: Array<OrderSiteItem>;
    total: number;
    limit: number;
    offset: number;
    legacy_primary: (OrderSiteLegacyPrimary | null);
};

