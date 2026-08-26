/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type NativeTemplateVersionItem = {
    id: number;
    template_id: number;
    version: number;
    status: string;
    renderer: string;
    source_filename?: (string | null);
    checksum_sha256: string;
    placeholder_schema: Record<string, any>;
    change_note?: (string | null);
    activated_at?: (string | null);
    created_at: string;
};

