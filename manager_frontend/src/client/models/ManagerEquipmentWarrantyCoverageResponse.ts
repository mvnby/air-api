/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerEquipmentWarrantyCoverageResponse = {
    id: number;
    equipment_id: number;
    component_id?: (number | null);
    policy_id?: (number | null);
    coverage_type: string;
    source: string;
    starts_at?: (string | null);
    expires_at?: (string | null);
    maintenance_required?: boolean;
    maintenance_interval_months?: (number | null);
    grace_period_days?: number;
    allowed_maintenance_provider?: string;
    next_maintenance_due_at?: (string | null);
    terms_snapshot?: (string | null);
    policy_snapshot?: Record<string, any>;
    decision_status?: string;
    decision_reason?: (string | null);
    decided_at?: (string | null);
    decided_by?: (string | null);
    time_status?: string;
    maintenance_status?: string;
    requires_manager_decision?: boolean;
    created_at: string;
    updated_at: string;
};
