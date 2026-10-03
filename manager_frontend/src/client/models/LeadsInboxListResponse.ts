/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LeadsInboxItemResponse } from './LeadsInboxItemResponse';
import type { Meta } from './Meta';
export type LeadsInboxListResponse = {
    items: Array<LeadsInboxItemResponse>;
    total: number;
    meta: Meta;
    pending_count?: number;
    unread_count?: number;
    /**
     * Counts across the selected scope, search and unread filter, before source filtering or pagination.
     */
    source_counts?: Record<string, number>;
};

