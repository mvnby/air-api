/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WebsiteInterestItem = {
    kind: 'product' | 'article' | 'service' | 'topic';
    page_path: string;
    title: string;
    active_seconds: number;
    product_id?: (number | null);
    topics?: (Array<string> | null);
};

