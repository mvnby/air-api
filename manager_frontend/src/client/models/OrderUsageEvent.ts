/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OrderUsageEvent = {
    metric: 'order_open' | 'proposal_open' | 'documents_open' | 'work_open' | 'payments_open' | 'customer_open' | 'object_edit' | 'equipment_open' | 'attachments_open' | 'product_add' | 'product_select' | 'product_description_edit' | 'product_remove' | 'service_add' | 'service_edit' | 'service_remove' | 'scenario_change' | 'autosave_toggle' | 'document_create' | 'payment_add';
    workflow: 'sales_installation' | 'work' | 'maintenance' | 'repair';
    party_kind: 'individual' | 'individual_entrepreneur' | 'company' | 'unknown';
    viewport: 'mobile' | 'tablet' | 'desktop';
};

