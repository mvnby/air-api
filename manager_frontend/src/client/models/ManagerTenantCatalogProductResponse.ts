/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerTenantCatalogProductResponse = {
    id: number;
    title: string;
    slug: string;
    brand_title?: (string | null);
    series_title?: (string | null);
    main_image?: (string | null);
    product_kind: string;
    is_inverter: boolean;
    power_cooling?: (number | null);
    offer_id?: (number | null);
    offer_status?: ('active' | 'disabled' | null);
    offer_is_published?: (boolean | null);
    effective_price?: (number | null);
    allowed: boolean;
};

