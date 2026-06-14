/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerMediaAssetResponse = {
    id: number;
    parent_asset_id?: (number | null);
    title: string;
    alt_text?: (string | null);
    description?: (string | null);
    kind: string;
    tags?: Array<string>;
    variant_type: string;
    url: string;
    original_url?: (string | null);
    source_filename?: (string | null);
    mime_type: string;
    storage_provider: string;
    processing_status: string;
    processing_error?: (string | null);
    content_hash?: (string | null);
    width?: (number | null);
    height?: (number | null);
    size_bytes?: number;
    usage_count?: number;
    created_by?: (string | null);
    created_at: string;
    updated_at: string;
};

