/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderTransferProductLine } from './ManagerOrderTransferProductLine';
import type { ManagerOrderTransferServiceLine } from './ManagerOrderTransferServiceLine';
export type ManagerOrderTransferProposal_Output = {
    source_id?: (number | null);
    name?: string;
    status?: string;
    is_selected?: boolean;
    is_archived?: boolean;
    sort_order?: number;
    product_lines?: Array<ManagerOrderTransferProductLine>;
    service_lines?: Array<ManagerOrderTransferServiceLine>;
};

