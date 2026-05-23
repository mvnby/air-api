/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CatalogImportJobStatusResponse = {
    job_id: string;
    status: string;
    stage: string;
    error?: (string | null);
    started_at?: (string | null);
    finished_at?: (string | null);
    input_total?: number;
    total?: number;
    processed?: number;
    pending?: number;
    success_count?: number;
    error_count?: number;
    current_url?: (string | null);
    current_title?: (string | null);
    successes?: Array<string>;
    errors?: Array<string>;
};

