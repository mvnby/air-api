/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerRestoreJobStatusResponse = {
    job_id: string;
    file_id: string;
    file_name: string;
    kind: string;
    status: string;
    stage: string;
    error?: (string | null);
    started_at?: (string | null);
    finished_at?: (string | null);
    safety_dump_path?: (string | null);
};

