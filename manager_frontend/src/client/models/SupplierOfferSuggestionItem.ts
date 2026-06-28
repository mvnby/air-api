/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SupplierOfferSuggestionCandidate } from './SupplierOfferSuggestionCandidate';
export type SupplierOfferSuggestionItem = {
    supplier_id: number;
    external_id: string;
    normalized_query: string;
    offer_tokens?: Array<string>;
    indoor_model_tokens?: Array<string>;
    outdoor_model_tokens?: Array<string>;
    candidates: Array<SupplierOfferSuggestionCandidate>;
    auto_eligible: boolean;
    reason: string;
};

