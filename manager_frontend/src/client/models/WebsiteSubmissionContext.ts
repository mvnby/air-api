/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Untrusted page/form references; these do not select or confirm ordered work.
 */
export type WebsiteSubmissionContext = {
    page_path: string;
    form_id: 'contact' | 'checkout' | 'installation_calculator' | 'installation_estimate' | 'repair_diagnostic' | 'product_availability' | 'multi_split';
    service_id?: (string | null);
    product_id?: (number | null);
};

