/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CompanyDomainResponse = {
    id: number;
    hostname: string;
    status: 'pending' | 'active' | 'disabled';
    is_primary: boolean;
    verified_at: (string | null);
};

