/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SupplierSyncRunResponse = {
    run_id: number;
    source_id: number;
    status: string;
    rows_total: number;
    rows_upserted: number;
    rows_skipped: number;
    rows_deactivated: number;
    error?: (string | null);
};

