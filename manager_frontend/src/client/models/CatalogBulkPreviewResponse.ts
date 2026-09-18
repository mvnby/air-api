/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogBulkPreviewItem } from './CatalogBulkPreviewItem';
export type CatalogBulkPreviewResponse = {
    token: string;
    items: Array<CatalogBulkPreviewItem>;
    changed_count: number;
    expires_in_seconds?: number;
};

