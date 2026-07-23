/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCatalogProductImageResponse } from './ManagerCatalogProductImageResponse';
import type { ManagerCatalogProductManualResponse } from './ManagerCatalogProductManualResponse';
import type { ManagerCatalogProductTagResponse } from './ManagerCatalogProductTagResponse';
import type { ManagerProductFeatureWorkspaceResponse } from './ManagerProductFeatureWorkspaceResponse';
export type ManagerCatalogProductItemResponse = {
    id: number;
    brand_id?: (number | null);
    series_id?: (number | null);
    title: string;
    slug: (string | null);
    price: number;
    old_price: (number | null);
    product_kind?: 'unknown' | 'complete_split_system' | 'indoor_unit' | 'outdoor_unit' | 'panel' | 'accessory' | 'consumable' | 'other';
    is_inverter: boolean;
    power_cooling: (number | null);
    main_image: (string | null);
    is_published: boolean;
    created_at: string;
    specs: Record<string, any>;
    gallery_images: Array<ManagerCatalogProductImageResponse>;
    manuals: Array<ManagerCatalogProductManualResponse>;
    tags: Array<ManagerCatalogProductTagResponse>;
    min_cost_byn?: (number | null);
    recommended_price_byn?: (number | null);
    margin_abs_preview?: (number | null);
    margin_pct_preview?: (number | null);
    vitebsk_qty?: number;
    minsk_qty?: number;
    availability_status?: string;
    features_workspace?: (ManagerProductFeatureWorkspaceResponse | null);
};

