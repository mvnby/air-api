/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Body_bulk_upload_local_images = {
    /**
     * JSON array of product ids
     */
    product_ids_json: string;
    files: Array<Blob>;
    is_installation?: boolean;
    set_main?: boolean;
};

