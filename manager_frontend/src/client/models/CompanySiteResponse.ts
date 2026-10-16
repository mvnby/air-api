/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CompanyDomainResponse } from './CompanyDomainResponse';
export type CompanySiteResponse = {
    id: number;
    slug: string;
    display_name: string;
    status: 'draft' | 'active' | 'disabled';
    city: (string | null);
    default_locale: string;
    currency: string;
    is_default: boolean;
    domains: Array<CompanyDomainResponse>;
};

