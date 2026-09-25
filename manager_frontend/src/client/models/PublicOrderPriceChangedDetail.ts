/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AcceptedProductLine_Output } from './AcceptedProductLine_Output';
export type PublicOrderPriceChangedDetail = {
    code?: string;
    reason: string;
    new_consent_required?: boolean;
    current_product_lines: Array<AcceptedProductLine_Output>;
    current_installation_preview: Record<string, any>;
    current_order_total?: (string | null);
};

