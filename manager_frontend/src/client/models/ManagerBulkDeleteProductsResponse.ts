/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerBulkDeleteProductsError } from './ManagerBulkDeleteProductsError';
export type ManagerBulkDeleteProductsResponse = {
    message: string;
    deleted_count: number;
    failed_count: number;
    errors?: Array<ManagerBulkDeleteProductsError>;
};

