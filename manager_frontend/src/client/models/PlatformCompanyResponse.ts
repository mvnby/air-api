/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CompanyOwnerResponse } from './CompanyOwnerResponse';
import type { CompanySiteResponse } from './CompanySiteResponse';
export type PlatformCompanyResponse = {
    id: number;
    slug: string;
    display_name: string;
    kind: string;
    status: 'active' | 'disabled';
    is_system: boolean;
    demo_read_only: boolean;
    updated_at: string;
    owners: Array<CompanyOwnerResponse>;
    active_staff_count: number;
    sites: Array<CompanySiteResponse>;
};

