/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SupplierSourceAnalysisRow } from './SupplierSourceAnalysisRow';
export type SupplierSourceAnalysisResponse = {
    source_id: number;
    rows_total: number;
    product_rows: number;
    section_rows: number;
    url_rows: number;
    skipped_rows: number;
    sample_rows?: Array<SupplierSourceAnalysisRow>;
    warnings?: Array<string>;
};

