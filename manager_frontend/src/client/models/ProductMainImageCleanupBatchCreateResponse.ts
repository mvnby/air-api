/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductMainImageCleanupBatchResponse } from './ProductMainImageCleanupBatchResponse';
import type { ProductMainImageCleanupItemResponse } from './ProductMainImageCleanupItemResponse';
import type { ProductMainImageCleanupSkippedExistingResponse } from './ProductMainImageCleanupSkippedExistingResponse';
export type ProductMainImageCleanupBatchCreateResponse = {
    batch: ProductMainImageCleanupBatchResponse;
    items?: Array<ProductMainImageCleanupItemResponse>;
    created_count: number;
    candidate_ready_count: number;
    skipped_count: number;
    failed_count: number;
    already_processed_count: number;
    skipped_existing?: Array<ProductMainImageCleanupSkippedExistingResponse>;
};

