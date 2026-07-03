/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MdvCatalogPreviewItemResponse } from './MdvCatalogPreviewItemResponse';
import type { MdvCatalogSpecKeyStatResponse } from './MdvCatalogSpecKeyStatResponse';
import type { MdvLegacyReplacePreviewResponse } from './MdvLegacyReplacePreviewResponse';
export type MdvCatalogPreviewResponse = {
    catalogs: Array<string>;
    total: number;
    by_catalog?: Record<string, number>;
    actions?: Record<string, number>;
    unmatched_source_urls?: number;
    raw_spec_key_count?: number;
    top_raw_spec_keys?: Array<MdvCatalogSpecKeyStatResponse>;
    top_unpromoted_spec_keys?: Array<MdvCatalogSpecKeyStatResponse>;
    samples?: Array<MdvCatalogPreviewItemResponse>;
    legacy_replace?: MdvLegacyReplacePreviewResponse;
    source_urls?: Record<string, string>;
    next_step?: string;
};

