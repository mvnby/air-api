/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotShopFeature } from './BotShopFeature';
import type { BotShopImage } from './BotShopImage';
import type { BotShopSpecification } from './BotShopSpecification';
import type { BotShopSpecificationGroup } from './BotShopSpecificationGroup';
export type BotShopProductResponse = {
    id: number;
    title: string;
    brand_title: (string | null);
    series_title: (string | null);
    thumbnail_url: (string | null);
    retail_price_byn: number;
    availability: 'in_stock' | 'out_of_stock';
    cooling_power_kw: (number | null);
    area_m2: (number | null);
    is_inverter: boolean;
    wifi: 'builtin' | 'ready' | 'none';
    public_site_url: (string | null);
    description: string;
    images: Array<BotShopImage>;
    summary_fields: Array<BotShopSpecification>;
    specification_groups: Array<BotShopSpecificationGroup>;
    features: Array<BotShopFeature>;
};

