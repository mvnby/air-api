/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerProductCollectionItemResponse = {
    id: number;
    product_id: number;
    position: number;
    is_pinned: boolean;
    editorial_note?: (string | null);
    product_title: string;
    product_slug: string;
    product_kind: 'unknown' | 'complete_split_system' | 'indoor_unit' | 'outdoor_unit' | 'panel' | 'accessory' | 'consumable' | 'other';
    is_published: boolean;
    price: number;
    main_image?: (string | null);
};

