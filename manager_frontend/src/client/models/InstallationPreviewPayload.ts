/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationExtraInput } from './InstallationExtraInput';
import type { InstallationInput } from './InstallationInput';
import type { InstallationSiteApproval } from './InstallationSiteApproval';
export type InstallationPreviewPayload = {
    installations: Array<InstallationInput>;
    site_extras?: Array<InstallationExtraInput>;
    approved_site_access?: Array<InstallationSiteApproval>;
    expected_revision?: (number | null);
};

