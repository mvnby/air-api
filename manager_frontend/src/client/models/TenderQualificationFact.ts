/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TenderEvidence } from './TenderEvidence';
export type TenderQualificationFact = {
    kind: 'work_scope' | 'equipment_count' | 'equipment_models' | 'maintenance_frequency' | 'maintenance_period' | 'execution_address' | 'installation_lines' | 'installation_access' | 'materials' | 'sole_proprietor_eligibility' | 'requirements' | 'estimated_budget' | 'offer_price' | 'submission_method' | 'submission_deadline' | 'procedure_type' | 'logistics';
    value: string;
    evidence?: (TenderEvidence | null);
    source?: 'document' | 'procedure_metadata';
    confidence: 'high' | 'medium' | 'low';
    work_type?: ('maintenance' | 'diagnostics' | 'repair' | 'installation' | 'supply_with_installation' | 'supply_only' | 'ventilation' | null);
    work_required?: (boolean | null);
    amount?: (string | null);
    currency?: (string | null);
    deadline_at?: (string | null);
};

