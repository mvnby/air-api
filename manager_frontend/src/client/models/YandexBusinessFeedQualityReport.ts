/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { YandexBusinessCollectionConflict } from './YandexBusinessCollectionConflict';
import type { YandexBusinessEditorialCategoryQuality } from './YandexBusinessEditorialCategoryQuality';
import type { YandexBusinessProductImageIssue } from './YandexBusinessProductImageIssue';
export type YandexBusinessFeedQualityReport = {
    product_offer_count: number;
    product_picture_count: number;
    service_offer_count: number;
    editorial_categories?: Array<YandexBusinessEditorialCategoryQuality>;
    categories_below_minimum_pictures?: Array<YandexBusinessEditorialCategoryQuality>;
    products_without_picture?: Array<YandexBusinessProductImageIssue>;
    image_generation_errors?: Array<YandexBusinessProductImageIssue>;
    collection_conflicts?: Array<YandexBusinessCollectionConflict>;
};

