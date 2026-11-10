/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConsumerDocumentTermsPayload } from './ConsumerDocumentTermsPayload';
import type { ContractAmendmentTerms_Output } from './ContractAmendmentTerms_Output';
import type { DocumentCustomerReadiness } from './DocumentCustomerReadiness';
import type { ManagedDocumentArtifactItem } from './ManagedDocumentArtifactItem';
import type { ParticipantStatementPayload } from './ParticipantStatementPayload';
import type { RepairDefect } from './RepairDefect';
import type { WaybillComposition_Output } from './WaybillComposition_Output';
export type ManagedDocumentItem = {
    consumer_terms?: (ConsumerDocumentTermsPayload | null);
    snapshot_total_amount?: (string | null);
    amendment_terms?: (ContractAmendmentTerms_Output | null);
    amendment_original_amount?: (string | null);
    amendment_new_total?: (string | null);
    amendment_change_amount?: (string | null);
    basis_number?: (string | null);
    basis_date?: (string | null);
    scope_product_line_ids?: (Array<number> | null);
    waybill_composition?: (WaybillComposition_Output | null);
    repair_defect?: (RepairDefect | null);
    receipt_note?: (string | null);
    warranty_equipment_id?: (number | null);
    participant_statement?: (ParticipantStatementPayload | null);
    customer_readiness?: (DocumentCustomerReadiness | null);
    maintenance_source_order_id?: (number | null);
    document_role_type?: ('seller_buyer' | 'executor_customer' | 'contractor_customer' | 'seller_payer' | 'executor_payer' | null);
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
    contract_act_number?: (number | null);
    official_date?: (string | null);
    issue_city?: (string | null);
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

