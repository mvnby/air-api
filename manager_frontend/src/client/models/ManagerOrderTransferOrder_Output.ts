/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderTransferCustomer } from './ManagerOrderTransferCustomer';
import type { ManagerOrderTransferCustomerBranch } from './ManagerOrderTransferCustomerBranch';
import type { ManagerOrderTransferPayment } from './ManagerOrderTransferPayment';
import type { ManagerOrderTransferProposal_Output } from './ManagerOrderTransferProposal_Output';
import type { ManagerOrderTransferWorkStage } from './ManagerOrderTransferWorkStage';
import type { PaymentCurrency } from './PaymentCurrency';
export type ManagerOrderTransferOrder_Output = {
    source_id?: (number | null);
    status?: string;
    lead_source?: (string | null);
    title?: (string | null);
    workflow_type?: string;
    repair_meta?: Record<string, any>;
    manager_labels?: Array<string>;
    created_at?: (string | null);
    next_followup_date?: (string | null);
    measurement_date?: (string | null);
    installation_date?: (string | null);
    comment?: (string | null);
    delivery_address?: (string | null);
    document_role_type?: (string | null);
    additional_conditions?: (string | null);
    closing_result?: (string | null);
    reject_reason?: (string | null);
    is_on_hold?: boolean;
    on_hold_reason?: (string | null);
    measurement_required?: boolean;
    measurement_result?: (string | null);
    proposal_status?: string;
    proposal_sent_at?: (string | null);
    equipment_status?: string;
    standard_install_kit_issued?: boolean;
    target_currency?: (PaymentCurrency | null);
    target_currency_amount?: (number | null);
    customer?: (ManagerOrderTransferCustomer | null);
    customer_branch?: (ManagerOrderTransferCustomerBranch | null);
    proposals?: Array<ManagerOrderTransferProposal_Output>;
    payments?: Array<ManagerOrderTransferPayment>;
    work_stages?: Array<ManagerOrderTransferWorkStage>;
};

