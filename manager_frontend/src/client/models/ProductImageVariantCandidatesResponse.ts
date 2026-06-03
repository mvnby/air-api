/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductImageVariantCandidateResponse } from './ProductImageVariantCandidateResponse';
export type ProductImageVariantCandidatesResponse = {
    dry_run?: boolean;
    variant_type: string;
    total_candidates: number;
    returned: number;
    candidates?: Array<ProductImageVariantCandidateResponse>;
};

