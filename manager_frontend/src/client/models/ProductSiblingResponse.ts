/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublicProductWarrantyResponse } from './PublicProductWarrantyResponse';
export type ProductSiblingResponse = {
    /**
     * Exact manufacturer designation from canonical model specs; null when unconfirmed.
     */
    model_code?: (string | null);
    /**
     * Confirmed nominal capacity class (e.g. 07, 09, 12); never inferred from title or kW. Null when unknown or inapplicable.
     */
    capacity_class?: (string | null);
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

