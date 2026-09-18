/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogManagementFilters } from './CatalogManagementFilters';
export type CatalogManagementQuery = {
    filters?: CatalogManagementFilters;
    page?: number;
    limit?: number;
    sort?: 'recommended' | 'newest' | 'price_asc' | 'price_desc' | 'title';
};

