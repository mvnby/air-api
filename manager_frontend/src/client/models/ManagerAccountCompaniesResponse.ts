/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerAccountCompany } from './ManagerAccountCompany';
export type ManagerAccountCompaniesResponse = {
    staff_user_id: (number | null);
    username: string;
    is_platform_owner: boolean;
    default_tenant_id: (number | null);
    items: Array<ManagerAccountCompany>;
    total: number;
    page: number;
    limit: number;
};

