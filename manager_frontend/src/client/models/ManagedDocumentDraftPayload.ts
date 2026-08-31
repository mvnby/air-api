/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActTermsPayload } from './ActTermsPayload';
import type { BusinessDocumentTermsPayload } from './BusinessDocumentTermsPayload';
import type { ConsumerDocumentTermsPayload } from './ConsumerDocumentTermsPayload';
export type ManagedDocumentDraftPayload = {
    legal_entity_id: number;
    document_type: string;
    issue_date: string;
    issue_city?: (string | null);
    template_id?: (number | null);
    proposal_id?: (number | null);
    base_document_id?: (number | null);
    base_customer_contract_id?: (number | null);
    scope_customer_branch_id?: (number | null);
    scope_title?: (string | null);
    scope_address?: (string | null);
    scope_service_line_ids?: Array<number>;
    scope_service_line_quantities?: Record<string, number>;
    scope_product_line_ids?: Array<number>;
    business_role?: (string | null);
    replaces_document_id?: (number | null);
    consumer_terms?: (ConsumerDocumentTermsPayload | null);
    business_terms?: (BusinessDocumentTermsPayload | null);
    act_terms?: (ActTermsPayload | null);
};

