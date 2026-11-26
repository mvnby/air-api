/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTenderEvidenceReport } from './ManagerTenderEvidenceReport';
export type TenderMarketEvidenceResult = {
    status: 'unrequested' | 'queued' | 'reading' | 'completed' | 'failed';
    checked_at?: (string | null);
    documents_source_url?: (string | null);
    report?: (ManagerTenderEvidenceReport | null);
    error?: (string | null);
};

