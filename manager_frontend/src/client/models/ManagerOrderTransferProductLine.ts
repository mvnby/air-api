/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderTransferProductRef } from './ManagerOrderTransferProductRef';
import type { OrderProductLogisticsComponent } from './OrderProductLogisticsComponent';
export type ManagerOrderTransferProductLine = {
    source_id?: (number | null);
    product: ManagerOrderTransferProductRef;
    title_snapshot?: (string | null);
    currency_snapshot?: (string | null);
    quantity: number;
    price: number;
    cost?: number;
    is_installation_included?: boolean;
    installation_price?: number;
    installation_details?: (Record<string, any> | null);
    logistics_components?: (Array<OrderProductLogisticsComponent> | null);
};

