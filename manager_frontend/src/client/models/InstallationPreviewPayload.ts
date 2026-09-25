/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationExtraInput } from './InstallationExtraInput';
import type { InstallationInput } from './InstallationInput';
export type InstallationPreviewPayload = {
    installations: Array<InstallationInput>;
    site_extras?: Array<InstallationExtraInput>;
    expected_revision?: (number | null);
};

