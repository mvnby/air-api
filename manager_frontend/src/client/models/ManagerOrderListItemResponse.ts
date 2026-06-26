/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallerResponse } from './ManagerInstallerResponse';
import type { OrderCustomerBranchBrief } from './OrderCustomerBranchBrief';
import type { OrderCustomerBrief } from './OrderCustomerBrief';
import type { OrderCustomerContractBrief } from './OrderCustomerContractBrief';
import type { PaymentCurrency } from './PaymentCurrency';
export type ManagerOrderListItemResponse = {
    id: number;
    status: string;
    lead_source?: (string | null);
    title?: (string | null);
    workflow_type?: string;
    repair_meta?: Record<string, any>;
    manager_labels?: Array<string>;
    created_at: string;
    updated_at?: (string | null);
    status_changed_at?: (string | null);
    next_followup_date?: (string | null);
    measurement_date?: (string | null);
    installation_date?: (string | null);
    total_amount: number;
    total_cost: number;
    margin: number;
    is_paid: boolean;
    comment?: (string | null);
    delivery_address?: (string | null);
    customer?: (OrderCustomerBrief | null);
    customer_branch?: (OrderCustomerBranchBrief | null);
    customer_contract_id?: (number | null);
    customer_contract?: (OrderCustomerContractBrief | null);
    document_role_type?: (string | null);
    effective_document_role_type?: string;
    additional_conditions?: (string | null);
    installer_id?: (number | null);
    installer?: (ManagerInstallerResponse | null);
    equipment_status?: string;
    standard_install_kit_issued?: boolean;
    target_currency?: (PaymentCurrency | null);
    target_currency_amount?: (number | null);
    target_currency_payments?: (number | null);
    closing_result?: (string | null);
    reject_reason?: (string | null);
    is_on_hold?: boolean;
    on_hold_reason?: (string | null);
    measurement_required?: boolean;
    measurer_id?: (number | null);
    measurement_result?: (string | null);
    proposal_status?: string;
    proposal_sent_at?: (string | null);
    negotiation_status?: string;
    negotiation_status_changed_at?: (string | null);
    execution_without_payment?: boolean;
    execution_without_payment_reason?: (string | null);
    auto_execution_on_payment?: boolean;
    total_payments?: number;
    balance_due?: number;
    readonly needs_attention: boolean;
    readonly awaiting_measurement: boolean;
    readonly client_thinking: boolean;
    readonly ready_for_execution: boolean;
};

