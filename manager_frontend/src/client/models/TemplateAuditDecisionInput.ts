/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TemplateAuditDecisionInput = {
    expected_revision: number;
    source_hash: string;
    context_hash: string;
    legal_sources_hash: string;
    status: 'proposal' | 'needs_legal_review' | 'accepted' | 'rejected' | 'fixed';
    reason: string;
};

