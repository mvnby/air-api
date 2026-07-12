/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationMetaPayload } from './InstallationMetaPayload';
export type CartItemPayload = {
    product_id?: (number | null);
    quantity?: number;
    with_installation?: boolean;
    installation_rate_id?: (number | null);
    installation_price?: number;
    installation_meta?: (InstallationMetaPayload | null);
    installation_options?: Array<string>;
};

