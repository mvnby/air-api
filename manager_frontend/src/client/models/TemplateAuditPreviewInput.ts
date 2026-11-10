/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TemplateAuditPreviewInput = {
    synthetic: boolean;
    label: string;
    values: Record<string, string>;
    conditions: Record<string, boolean>;
    table_rows?: Record<string, Array<Record<string, string>>>;
    format?: 'docx' | 'pdf';
    source_hash: string;
    context_hash: string;
    legal_sources_hash: string;
};

