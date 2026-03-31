/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Universal import payload — accepts URLs from any supported source
 * (onliner.by, aircond.by, etc.).  ImporterService routes by domain.
 */
export type CatalogImportPayload = {
    urls: Array<string>;
    with_related?: boolean;
    update_existing?: boolean;
};

