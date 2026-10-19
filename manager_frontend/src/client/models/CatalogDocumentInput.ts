/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CatalogDocumentInput = {
    title: string;
    url: string;
    kind?: 'catalog' | 'operation' | 'installation' | 'service' | 'brochure' | 'certificate' | 'other';
    source_url?: (string | null);
    language?: (string | null);
    year?: (number | null);
    visibility?: 'public' | 'internal';
    inherit_to_products?: boolean;
};

