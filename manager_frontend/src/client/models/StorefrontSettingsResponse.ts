/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ServiceDirectionSetting } from './ServiceDirectionSetting';
import type { StorefrontSiteSettingsResponse } from './StorefrontSiteSettingsResponse';
export type StorefrontSettingsResponse = {
    site: StorefrontSiteSettingsResponse;
    services: Array<ServiceDirectionSetting>;
    version: number;
    updated_at?: (string | null);
};

