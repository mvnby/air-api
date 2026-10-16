/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerAccountCompany = {
    tenant_id: number;
    slug: string;
    display_name: string;
    role: string;
    membership_id: (number | null);
    access_kind: 'membership' | 'platform_support';
    is_system: boolean;
    demo_read_only: boolean;
    default_storefront_slug: string;
};

