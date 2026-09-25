/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationExtraInput } from './InstallationExtraInput';
import type { TypedInstallationProfile_Input } from './TypedInstallationProfile_Input';
export type InstallationInput = {
    product_id?: (number | null);
    typed_profile?: (TypedInstallationProfile_Input | null);
    work_kind?: 'standard' | 'prelaid_route';
    key: string;
    display_label?: (string | null);
    route_length_m: (number | string);
    holes_by_type: Record<string, (number | string)>;
    extras?: Array<InstallationExtraInput>;
};

