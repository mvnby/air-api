/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderProductLogisticsComponent } from './OrderProductLogisticsComponent';
export type ManagerOrderProductLinePayload = {
    link_id?: (number | null);
    proposal_id?: (number | null);
    /**
     * Catalog identity; null for a proposal-only manual product.
     */
    product_id?: (number | null);
    /**
     * Required snapshot name for a manual product; never creates a catalog product.
     */
    title?: (string | null);
    client_description?: (string | null);
    quantity: number;
    price: number;
    cost?: (number | null);
    logistics_components?: (Array<OrderProductLogisticsComponent> | null);
};

