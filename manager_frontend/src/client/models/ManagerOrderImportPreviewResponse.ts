/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderImportCustomerMatch } from './ManagerOrderImportCustomerMatch';
import type { ManagerOrderImportProductMatch } from './ManagerOrderImportProductMatch';
export type ManagerOrderImportPreviewResponse = {
    orders_count: number;
    products_total: number;
    products_matched: number;
    products_missing: number;
    customers?: Array<ManagerOrderImportCustomerMatch>;
    products?: Array<ManagerOrderImportProductMatch>;
    can_import: boolean;
    warnings?: Array<string>;
};

