/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SourceCustomerDraft } from './SourceCustomerDraft';
import type { SourceObjectDraft } from './SourceObjectDraft';
export type ManagerOrderSourceApply = {
    customer_action: string;
    customer_id?: (number | null);
    customer?: (SourceCustomerDraft | null);
    work_summary?: (string | null);
    equipment_details?: (string | null);
    objects?: (Array<SourceObjectDraft> | null);
    document_ids?: Array<string>;
    analysis_source?: (string | null);
    analyzed_document_ids?: (Array<string> | null);
};

