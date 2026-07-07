/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductSeriesBrandFeatureResponse } from './ProductSeriesBrandFeatureResponse';
export type PublicBrandDetailResponse = {
    id: number;
    title: string;
    slug: string;
    logo_url?: (string | null);
    description?: (string | null);
    products_count: number;
    sort_order: number;
    features?: Array<ProductSeriesBrandFeatureResponse>;
};

