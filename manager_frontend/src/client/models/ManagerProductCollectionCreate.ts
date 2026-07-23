/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerProductCollectionCreate = {
    internal_name: string;
    public_title: string;
    public_description?: (string | null);
    public_badge?: (string | null);
    cta_label?: (string | null);
    cta_url?: (string | null);
    editorial_note?: (string | null);
    status?: 'draft' | 'published' | 'archived';
    mode?: string;
    min_items?: number;
    max_items?: number;
    fallback_collection_id?: (number | null);
    starts_at?: (string | null);
    ends_at?: (string | null);
    slug?: (string | null);
};

