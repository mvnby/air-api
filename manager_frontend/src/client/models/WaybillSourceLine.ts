/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WaybillComponent } from './WaybillComponent';
export type WaybillSourceLine = {
    order_product_line_id: number;
    components: (Array<WaybillComponent> | null);
    product_id: (number | null);
    title: string;
    country: string;
    quantity: number;
    unit_price: string;
};

