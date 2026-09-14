/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ServiceDirectionSetting } from './ServiceDirectionSetting';
import type { StorefrontSiteSettings } from './StorefrontSiteSettings';
export type StorefrontSettingsResponse = {
    site: StorefrontSiteSettings;
    services: Array<ServiceDirectionSetting>;
    version: number;
    updated_at?: (string | null);
};

