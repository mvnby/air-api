/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotCatalogSpecsResponse } from './BotCatalogSpecsResponse';
/**
 * Small, stable product projection used by Telegram catalog cards.
 */
export type BotCatalogProductResponse = {
    id: number;
    title: string;
    slug?: string;
    description?: string;
    price: number;
    specs?: BotCatalogSpecsResponse;
    main_image?: (string | null);
    categories?: Array<string>;
    vitebsk_qty?: number;
    minsk_qty?: number;
    availability_status?: string;
};

