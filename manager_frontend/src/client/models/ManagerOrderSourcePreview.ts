/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SourceCustomerDraft } from './SourceCustomerDraft';
import type { SourceDocumentPreview } from './SourceDocumentPreview';
import type { SourceEquipmentPrefillResult } from './SourceEquipmentPrefillResult';
import type { SourceObjectDraft } from './SourceObjectDraft';
import type { SourceScenarioDraft } from './SourceScenarioDraft';
export type ManagerOrderSourcePreview = {
    order_id: number;
    source_code: string;
    external_id: string;
    source_url?: (string | null);
    title?: (string | null);
    deadline_at?: (string | null);
    estimated_value?: (number | null);
    customer: SourceCustomerDraft;
    existing_customer_id?: (number | null);
    current_scenario?: (SourceScenarioDraft | null);
    suggested_scenario?: (SourceScenarioDraft | null);
    work_summary?: (string | null);
    equipment_details?: (string | null);
    objects?: Array<SourceObjectDraft>;
    documents?: Array<SourceDocumentPreview>;
    field_sources?: Record<string, string>;
    warnings?: Array<string>;
    analysis_source?: string;
    analyzed_document_ids?: Array<string>;
    equipment_prefill?: (SourceEquipmentPrefillResult | null);
};

