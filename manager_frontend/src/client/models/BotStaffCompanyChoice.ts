/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotStaffSiteChoice } from './BotStaffSiteChoice';
export type BotStaffCompanyChoice = {
    tenant_id: number;
    tenant_slug: string;
    tenant_name: string;
    primary_role: string;
    permissions: Array<string>;
    storefronts: Array<BotStaffSiteChoice>;
};

