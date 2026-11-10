/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TemplateAuditPreviewContext = {
    synthetic: boolean;
    label: string;
    values: Record<string, string>;
    conditions: Record<string, boolean>;
    table_rows?: Record<string, Array<Record<string, string>>>;
    format?: 'docx' | 'pdf';
    source_hash: string;
    context_hash: string;
    legal_sources_hash: string;
    field_labels: Record<string, string>;
    condition_labels: Record<string, string>;
    table_labels: Record<string, string>;
    row_field_labels: Record<string, string>;
};

