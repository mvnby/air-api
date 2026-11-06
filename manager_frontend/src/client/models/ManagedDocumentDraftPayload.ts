/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActTermsPayload } from './ActTermsPayload';
import type { BusinessDocumentTermsPayload_Input } from './BusinessDocumentTermsPayload_Input';
import type { ConsumerDocumentTermsPayload } from './ConsumerDocumentTermsPayload';
import type { ParticipantStatementPayload } from './ParticipantStatementPayload';
import type { RepairDefect } from './RepairDefect';
import type { TransportTermsPayload } from './TransportTermsPayload';
import type { WaybillComposition_Input } from './WaybillComposition_Input';
export type ManagedDocumentDraftPayload = {
    /**
     * Для совместимости. Неизвестные реквизиты можно вписать от руки без дополнительного подтверждения.
     */
    allow_incomplete_customer?: boolean;
    document_role_type?: ('seller_buyer' | 'executor_customer' | 'contractor_customer' | 'seller_payer' | 'executor_payer' | null);
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
    /**
     * Order product line IDs from the selected proposal. For a customer-owned equipment installation or maintenance/repair act with product lines, explicitly pass [] for work only or the supplied materials' IDs.
     */
    scope_product_line_ids?: Array<number>;
    business_role?: (string | null);
    replaces_document_id?: (number | null);
    consumer_terms?: (ConsumerDocumentTermsPayload | null);
    business_terms?: (BusinessDocumentTermsPayload_Input | null);
    act_terms?: (ActTermsPayload | null);
    transport_terms?: (TransportTermsPayload | null);
    repair_defect?: (RepairDefect | null);
    waybill_composition?: (WaybillComposition_Input | null);
    receipt_note?: (string | null);
    warranty_equipment_id?: (number | null);
    participant_statement?: (ParticipantStatementPayload | null);
};

