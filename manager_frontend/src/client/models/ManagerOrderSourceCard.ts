/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SourceEquipmentPrefillResult } from './SourceEquipmentPrefillResult';
import type { SourceInstallationFact } from './SourceInstallationFact';
import type { SourceObjectDraft } from './SourceObjectDraft';
import type { SourceOriginalFile } from './SourceOriginalFile';
import type { SourceSubmissionDraft } from './SourceSubmissionDraft';
export type ManagerOrderSourceCard = {
    order_id: number;
    source: string;
    external_id: string;
    title?: (string | null);
    source_url?: (string | null);
    submission?: SourceSubmissionDraft;
    work_summary?: (string | null);
    equipment_details?: (string | null);
    objects?: Array<SourceObjectDraft>;
    originals?: Array<SourceOriginalFile>;
    equipment_prefill?: (SourceEquipmentPrefillResult | null);
    installation_facts?: Array<SourceInstallationFact>;
};

