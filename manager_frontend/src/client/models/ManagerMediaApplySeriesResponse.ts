/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerMediaApplySeriesResponse = {
    message: string;
    dry_run?: boolean;
    source_product_id: number;
    series_id: number;
    series_title?: (string | null);
    updated_products: number;
    images_applied: number;
    main_image?: (string | null);
    replaced_links?: number;
    obsolete_urls?: Array<string>;
    preserved_installation_links?: number;
    deleted_files_count?: number;
};

