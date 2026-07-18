/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerCatalogQualityGroupResponse = {
    key: string;
    label: string;
    count: number;
    average_score: number;
    critical_products?: number;
    in_stock_products?: number;
    media_problem_products?: number;
    spec_problem_products?: number;
    shared_main_image_products?: number;
    shared_main_image_width?: (number | null);
    shared_main_image_height?: (number | null);
};

