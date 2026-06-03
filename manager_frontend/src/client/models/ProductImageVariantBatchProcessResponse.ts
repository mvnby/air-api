/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductImageVariantCandidateResponse } from './ProductImageVariantCandidateResponse';
import type { ProductImageVariantResponse } from './ProductImageVariantResponse';
export type ProductImageVariantBatchProcessResponse = {
    dry_run: boolean;
    variant_type: string;
    total_candidates?: number;
    returned?: number;
    candidates?: Array<ProductImageVariantCandidateResponse>;
    processed?: number;
    errors?: Array<Record<string, any>>;
    variants?: Array<ProductImageVariantResponse>;
};

