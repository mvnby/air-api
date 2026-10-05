/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SourceEquipmentPrefillResult } from './SourceEquipmentPrefillResult';
import type { SourceObjectDraft } from './SourceObjectDraft';
import type { SourceSubmissionDraft } from './SourceSubmissionDraft';
export type ManagerOrderSourceEnrichment = {
    source: string;
    external_id: string;
    submission?: SourceSubmissionDraft;
    work_summary?: (string | null);
    equipment_details?: (string | null);
    objects?: Array<SourceObjectDraft>;
    equipment_prefill?: (SourceEquipmentPrefillResult | null);
    customer_branch_ids?: Array<number>;
    analysis_source?: (string | null);
    analyzed_document_ids?: Array<string>;
};

