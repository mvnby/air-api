/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCustomerBranchItemResponse } from './ManagerCustomerBranchItemResponse';
export type ManagerCatalogCustomerItemResponse = {
    id: number;
    name: (string | null);
    phone: (string | null);
    email: (string | null);
    type: string;
    inn: (string | null);
    kpp?: (string | null);
    full_legal_name: (string | null);
    legal_address: (string | null);
    actual_address?: (string | null);
    city?: (string | null);
    iban: (string | null);
    bic: (string | null);
    bank_name: (string | null);
    signer_position?: (string | null);
    signer_name?: (string | null);
    acting_basis?: (string | null);
    signing_mode?: (string | null);
    last_delivery_address?: (string | null);
    created_at: (string | null);
    order_count: number;
    is_favorite?: boolean;
    branches?: Array<ManagerCustomerBranchItemResponse>;
};

