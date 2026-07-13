/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerWarrantyPolicyResponse = {
    id: number;
    name: string;
    coverage_type?: string;
    supplier_id?: (number | null);
    brand_id?: (number | null);
    series_id?: (number | null);
    product_id?: (number | null);
    supplier_name?: (string | null);
    brand_title?: (string | null);
    series_title?: (string | null);
    series_brand_id?: (number | null);
    product_title?: (string | null);
    duration_months?: (number | null);
    start_event?: string;
    maintenance_required?: boolean;
    maintenance_interval_months?: (number | null);
    grace_period_days?: number;
    allowed_maintenance_provider?: string;
    terms?: (string | null);
    effective_from?: (string | null);
    effective_until?: (string | null);
    is_active?: boolean;
    created_at: string;
    updated_at: string;
};
