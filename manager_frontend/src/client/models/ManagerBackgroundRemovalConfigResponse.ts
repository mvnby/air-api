/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerBackgroundRemovalModelOption } from './ManagerBackgroundRemovalModelOption';
import type { ManagerBackgroundRemovalProviderOption } from './ManagerBackgroundRemovalProviderOption';
export type ManagerBackgroundRemovalConfigResponse = {
    default_provider: string;
    default_rembg_model: string;
    preload_models: Array<string>;
    provider_options: Array<ManagerBackgroundRemovalProviderOption>;
    rembg_models: Array<ManagerBackgroundRemovalModelOption>;
};

