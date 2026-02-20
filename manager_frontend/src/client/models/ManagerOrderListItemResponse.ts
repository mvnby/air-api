/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallerResponse } from './ManagerInstallerResponse';
import type { OrderCustomerBrief } from './OrderCustomerBrief';
export type ManagerOrderListItemResponse = {
    id: number;
    status: string;
    created_at: string;
    updated_at?: (string | null);
    next_followup_date?: (string | null);
    assessment_date?: (string | null);
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
};

