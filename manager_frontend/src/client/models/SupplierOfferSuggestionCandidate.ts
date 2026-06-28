/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SupplierOfferSuggestionCandidate = {
    product_id: number;
    title: string;
    price: number;
    score?: number;
    confidence?: number;
    matched_tokens?: Array<string>;
    missing_tokens?: Array<string>;
    explanations?: Array<string>;
    score_breakdown?: Record<string, number>;
};

