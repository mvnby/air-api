/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Body_upload_manager_order_document = {
    file: Blob;
    document_type?: ('contract' | 'technical_inspection_act' | 'defect_act' | 'act' | 'other' | null);
    number?: (string | null);
    document_date?: (string | null);
    external_status?: ('received' | 'signed' | null);
    site_id?: (number | null);
    equipment_ids?: (Array<number> | null);
    base_document_id?: (number | null);
    proposal_id?: (number | null);
};

