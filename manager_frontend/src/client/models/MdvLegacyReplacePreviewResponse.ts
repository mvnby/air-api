/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MdvLegacyReplaceSampleResponse } from './MdvLegacyReplaceSampleResponse';
export type MdvLegacyReplacePreviewResponse = {
    enabled?: boolean;
    catalogs?: Array<string>;
    total?: number;
    by_catalog?: Record<string, number>;
    deletable_count?: number;
    keep_for_update_count?: number;
    deleted_count?: number;
    archived_count?: number;
    samples?: Array<MdvLegacyReplaceSampleResponse>;
};

