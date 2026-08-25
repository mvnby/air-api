/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationDiscountStatus } from './ManagerInstallationDiscountStatus';
export type ManagerInstallationDiscountProductResponse = {
    product_id: number;
    title: string;
    slug: string;
    main_image?: (string | null);
    retail_price: number;
    purchase_cost?: (number | null);
    margin?: (number | null);
    configured_discount: number;
    applied_discount: number;
    has_override: boolean;
    status: ManagerInstallationDiscountStatus;
    status_note: string;
};

