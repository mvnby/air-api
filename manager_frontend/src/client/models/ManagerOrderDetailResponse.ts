/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallerResponse } from './ManagerInstallerResponse';
import type { ManagerOrderDocumentItem } from './ManagerOrderDocumentItem';
import type { OrderCustomerBrief } from './OrderCustomerBrief';
import type { OrderProductLineResponse } from './OrderProductLineResponse';
import type { OrderServiceLineResponse } from './OrderServiceLineResponse';
import type { PaymentResponse } from './PaymentResponse';
export type ManagerOrderDetailResponse = {
    id: number;
    status: string;
    created_at: string;
    updated_at?: (string | null);
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
    installer_id?: (number | null);
    installer?: (ManagerInstallerResponse | null);
    closing_result?: (string | null);
    reject_reason?: (string | null);
    is_on_hold?: boolean;
    on_hold_reason?: (string | null);
    measurement_required?: boolean;
    proposal_sent_at?: (string | null);
    total_payments?: number;
    balance_due?: number;
    product_lines?: Array<OrderProductLineResponse>;
    service_lines?: Array<OrderServiceLineResponse>;
    documents?: Array<ManagerOrderDocumentItem>;
    payments?: Array<PaymentResponse>;
};

