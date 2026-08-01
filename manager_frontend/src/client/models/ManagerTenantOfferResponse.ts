/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerTenantOfferResponse = {
    id: number;
    storefront_id: number;
    product_id: number;
    product_title: string;
    product_slug: string;
    price: number;
    old_price?: (number | null);
    is_published: boolean;
    status: 'active' | 'disabled';
    created_by_username: string;
    updated_by_username: string;
    created_at: string;
    updated_at: string;
};

