/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerMediaBackfillReferencedAssetsResponse = {
    dry_run: boolean;
    include_remote: boolean;
    limit: number;
    references_seen: number;
    unique_urls_seen: number;
    planned: number;
    created: number;
    skipped_count: number;
    items?: Array<Record<string, any>>;
    skipped?: Array<Record<string, any>>;
    errors?: Array<Record<string, any>>;
};

