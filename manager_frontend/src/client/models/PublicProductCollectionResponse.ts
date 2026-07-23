/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublicProductCollectionItemResponse } from './PublicProductCollectionItemResponse';
export type PublicProductCollectionResponse = {
    slug: string;
    title: string;
    description?: (string | null);
    badge?: (string | null);
    cta_label?: (string | null);
    cta_url?: (string | null);
    position: number;
    updated_at: string;
    items?: Array<PublicProductCollectionItemResponse>;
};

