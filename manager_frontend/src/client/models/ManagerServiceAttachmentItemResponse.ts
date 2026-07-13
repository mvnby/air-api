/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerServiceAttachmentItemResponse = {
    id?: (number | null);
    legacy_key?: (string | null);
    legacy?: boolean;
    file_kind?: string;
    category?: string;
    filename: string;
    mime_type?: string;
    size_bytes?: number;
    caption?: (string | null);
    transcript?: (string | null);
    source?: string;
    processing_status?: string;
    processing_error?: (string | null);
    captured_at?: (string | null);
    created_at: string;
    preview_available?: boolean;
    equipment_id?: (number | null);
    component_id?: (number | null);
    service_history_id?: (number | null);
};

