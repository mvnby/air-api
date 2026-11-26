/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AnalyzedTenderFile } from './AnalyzedTenderFile';
import type { TenderQualificationFact } from './TenderQualificationFact';
export type ManagerTenderEvidenceReport = {
    documents: Array<AnalyzedTenderFile>;
    unselected_count: number;
    document_coverage_complete: boolean;
    analysis_status: 'completed' | 'local_evidence_only' | 'not_requested';
    findings: Array<TenderQualificationFact>;
};

