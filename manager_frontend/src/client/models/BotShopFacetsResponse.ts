/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotShopBrandFacet } from './BotShopBrandFacet';
import type { BotShopCoolingFacet } from './BotShopCoolingFacet';
import type { BotShopFeatureFacet } from './BotShopFeatureFacet';
import type { BotShopSeriesFacet } from './BotShopSeriesFacet';
export type BotShopFacetsResponse = {
    total: number;
    brands: Array<BotShopBrandFacet>;
    series: Array<BotShopSeriesFacet>;
    cooling_btu_classes: Array<BotShopCoolingFacet>;
    features: Array<BotShopFeatureFacet>;
};

