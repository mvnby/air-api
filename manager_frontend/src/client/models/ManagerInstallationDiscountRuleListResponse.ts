/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationDiscountPolicyResponse } from './ManagerInstallationDiscountPolicyResponse';
import type { ManagerInstallationDiscountProductResponse } from './ManagerInstallationDiscountProductResponse';
export type ManagerInstallationDiscountRuleListResponse = {
    policy: ManagerInstallationDiscountPolicyResponse;
    items: Array<ManagerInstallationDiscountProductResponse>;
    page: number;
    limit: number;
    total: number;
};

