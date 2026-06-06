/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductMainImageCleanupItemResponse } from './ProductMainImageCleanupItemResponse';
export type ProductMainImageCleanupDecisionResponse = {
    updated_count: number;
    skipped_count: number;
    skipped?: Array<Record<string, any>>;
    items?: Array<ProductMainImageCleanupItemResponse>;
};

