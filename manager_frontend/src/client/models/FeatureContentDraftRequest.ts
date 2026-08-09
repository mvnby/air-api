/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Only immutable context and source text are sent; entity fields are never saved.
 */
export type FeatureContentDraftRequest = {
    mode: 'from_source' | 'polish_text';
    source_url?: (string | null);
    full_description?: (string | null);
    name?: (string | null);
    brand_name?: (string | null);
    category_name?: (string | null);
};

