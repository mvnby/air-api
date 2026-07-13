/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MediaWorkerClaimedJobResponse = {
    job_id: string;
    source_asset_id: number;
    result_asset_id?: (number | null);
    operation: string;
    status: string;
    stage: string;
    provider?: (string | null);
    rembg_model?: (string | null);
    priority: number;
    attempts: number;
    worker_id?: (string | null);
    request_payload?: Record<string, any>;
    result_payload?: Record<string, any>;
    error?: (string | null);
    source_url?: (string | null);
    source_title?: (string | null);
    result_url?: (string | null);
    created_by?: (string | null);
    created_at: string;
    started_at?: (string | null);
    lease_expires_at?: (string | null);
    finished_at?: (string | null);
    updated_at: string;
    lease_token: string;
};

