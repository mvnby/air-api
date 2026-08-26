/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagedDocumentArtifactItem } from './ManagedDocumentArtifactItem';
export type ManagedDocumentItem = {
    id: number;
    order_id: number;
    legal_entity_id?: (number | null);
    proposal_id?: (number | null);
    doc_type: string;
    business_role?: (string | null);
    status: string;
    provider: string;
    internal_reference?: (string | null);
    official_series?: (string | null);
    official_period_key?: (string | null);
    official_number?: (string | null);
    official_full_number?: (string | null);
    official_date?: (string | null);
    display_number: string;
    date: string;
    document_template_id?: (number | null);
    template_version_id?: (number | null);
    base_document_id?: (number | null);
    base_customer_contract_id?: (number | null);
    replaces_document_id?: (number | null);
    issued_at?: (string | null);
    sent_at?: (string | null);
    signed_at?: (string | null);
    voided_at?: (string | null);
    void_reason?: (string | null);
    google_edit_url?: (string | null);
    created_at: string;
    artifacts?: Array<ManagedDocumentArtifactItem>;
};

