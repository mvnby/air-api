/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActTermsPayload } from './ActTermsPayload';
import type { DocumentRoleType } from './DocumentRoleType';
export type PrepareOrderCompletionActPayload = {
    idempotency_key: string;
    site_ids: Array<number>;
    proposal_id: number;
    expected_proposal_version: string;
    legal_entity_id: number;
    issue_date: string;
    issue_city?: (string | null);
    document_role_type?: (DocumentRoleType | null);
    base_document_id?: (number | null);
    base_customer_contract_id?: (number | null);
    act_terms: ActTermsPayload;
    template_id?: (number | null);
    scope_service_line_ids?: Array<number>;
    scope_service_line_quantities?: Record<string, number>;
    scope_product_line_ids?: Array<number>;
    scope_product_line_quantities?: Record<string, number>;
    replaces_document_id?: (number | null);
    expected_document_revision?: (string | null);
};

