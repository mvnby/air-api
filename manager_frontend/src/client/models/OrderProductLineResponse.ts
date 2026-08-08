/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderProductLogisticsComponent } from './OrderProductLogisticsComponent';
import type { ProductLogisticsComponentTemplate } from './ProductLogisticsComponentTemplate';
export type OrderProductLineResponse = {
    id: number;
    proposal_id?: (number | null);
    product_id?: (number | null);
    product_title: string;
    title_snapshot?: (string | null);
    currency_snapshot?: (string | null);
    quantity: number;
    price: number;
    cost: number;
    is_installation_included: boolean;
    installation_price: number;
    line_total: number;
    product_country?: (string | null);
    product_logistics_components?: Array<ProductLogisticsComponentTemplate>;
    logistics_components?: Array<OrderProductLogisticsComponent>;
};

