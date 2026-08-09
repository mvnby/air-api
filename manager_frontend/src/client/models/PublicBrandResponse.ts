/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublicFeaturedSeriesResponse } from './PublicFeaturedSeriesResponse';
export type PublicBrandResponse = {
    id: number;
    title: string;
    slug: string;
    logo_url?: (string | null);
    short_description?: (string | null);
    description?: (string | null);
    products_count: number;
    sort_order: number;
    featured_series?: Array<PublicFeaturedSeriesResponse>;
};

