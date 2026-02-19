/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCatalogProductImageResponse } from './ManagerCatalogProductImageResponse';
import type { ManagerCatalogProductTagResponse } from './ManagerCatalogProductTagResponse';
export type ManagerCatalogProductItemResponse = {
    id: number;
    title: string;
    slug: (string | null);
    price: number;
    old_price: (number | null);
    area: number;
    is_inverter: boolean;
    power_cooling: (number | null);
    main_image: (string | null);
    is_published: boolean;
    created_at: string;
    specs: Record<string, any>;
    gallery_images: Array<ManagerCatalogProductImageResponse>;
    tags: Array<ManagerCatalogProductTagResponse>;
};

