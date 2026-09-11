/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublicProductWarrantyResponse } from './PublicProductWarrantyResponse';
export type ProductSiblingResponse = {
    id: number;
    title: string;
    slug: (string | null);
    price: number;
    old_price: (number | null);
    specs?: Record<string, any>;
    is_inverter: boolean;
    main_image: (string | null);
    warranty?: (PublicProductWarrantyResponse | null);
};

