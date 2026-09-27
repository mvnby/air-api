/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotQuickOrderAddressCheck } from './BotQuickOrderAddressCheck';
export type BotQuickOrderDraft = {
    customer_id?: (number | null);
    customer_type?: ('individual' | 'individual_entrepreneur' | 'company' | null);
    name?: (string | null);
    contact_name?: (string | null);
    contact_phone?: (string | null);
    contact_email?: (string | null);
    phone?: (string | null);
    email?: (string | null);
    inn?: (string | null);
    customer_branch_id?: (number | null);
    address?: (string | null);
    legal_address?: (string | null);
    workflow_type?: ('sales_installation' | 'service_work' | 'maintenance' | 'repair' | null);
    service_type?: ('turnkey' | 'install_only' | 'pre_install' | 'maintenance' | 'repair' | 'dismantling' | null);
    service_label: string;
    target_date?: (string | null);
    target_date_precision?: ('date' | 'datetime' | null);
    equipment_summary?: (string | null);
    equipment_count?: (number | null);
    equipment_type?: (string | null);
    field_sources?: Record<string, 'ai' | 'fallback' | 'user' | 'customer'>;
    request_text: string;
    parser?: 'fallback' | 'ai';
    address_check?: (BotQuickOrderAddressCheck | null);
};

