/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ServiceCatalogCounts } from './ServiceCatalogCounts';
export type ManagerServiceCatalogCloneResponse = {
    status: 'cloned' | 'already_cloned';
    cloned_counts: ServiceCatalogCounts;
    source_fingerprint: string;
};

