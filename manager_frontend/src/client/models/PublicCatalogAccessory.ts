/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PublicCatalogAccessory = {
    product_id: number;
    title: string;
    slug: string;
    accessory_type?: (string | null);
    main_image?: (string | null);
    price: number;
    old_price?: (number | null);
    availability_status?: (string | null);
    delivery_min_days?: (number | null);
    delivery_max_days?: (number | null);
    compatibility_source: 'series' | 'product';
    /**
     * Wi-Fi modules are suggested only for a model explicitly marked Wi-Fi Ready; compatibility alone never changes capability.
     */
    suggested_for_purchase?: boolean;
};

