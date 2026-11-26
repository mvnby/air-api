/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTenderEvidenceReport } from './ManagerTenderEvidenceReport';
export type ManagerTenderEvidenceJob = {
    job_id: string;
    status: 'reading' | 'analyzing' | 'completed' | 'failed';
    processed: number;
    total: number;
    report?: (ManagerTenderEvidenceReport | null);
    error?: (string | null);
};

