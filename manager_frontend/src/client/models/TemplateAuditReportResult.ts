/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TemplateAuditReportResult = {
    id: number;
    template_id: number;
    template_name?: string;
    version_number?: number;
    version_id: number;
    legal_entity_id: number;
    customer_id: (number | null);
    revision: number;
    source_hash: string;
    context_hash: string;
    legal_sources_hash: string;
    checked_at: string;
    coverage: Record<string, any>;
    checklist: Record<string, string>;
    findings: Array<Record<string, any>>;
    proposals: Array<Record<string, any>>;
    stale: boolean;
    stale_reasons: Array<string>;
    legal_currency: 'matches_supplied_hash' | 'changed' | 'requires_external_recheck';
    manager_url: string;
};

