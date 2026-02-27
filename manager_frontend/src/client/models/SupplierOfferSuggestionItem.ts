/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SupplierOfferSuggestionCandidate } from './SupplierOfferSuggestionCandidate';
export type SupplierOfferSuggestionItem = {
    supplier_id: number;
    external_id: string;
    normalized_query: string;
    candidates: Array<SupplierOfferSuggestionCandidate>;
    auto_eligible: boolean;
    reason: string;
};

