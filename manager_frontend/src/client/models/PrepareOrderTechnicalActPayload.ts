/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TechnicalActInspection } from './TechnicalActInspection';
export type PrepareOrderTechnicalActPayload = {
    idempotency_key: string;
    expected_site_version: number;
    document_type: 'technical_inspection_act' | 'defect_act';
    inspections: Array<TechnicalActInspection>;
    legal_entity_id: number;
    issue_date: string;
    base_document_id?: (number | null);
    base_customer_contract_id?: (number | null);
    template_id?: (number | null);
    replaces_document_id?: (number | null);
};

