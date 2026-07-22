/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FeatureLinkPayload } from './FeatureLinkPayload';
import type { PublicFeatureResponse } from './PublicFeatureResponse';
export type ManagerProductFeatureWorkspaceResponse = {
    effective?: Array<PublicFeatureResponse>;
    automatic_suggestions?: Array<PublicFeatureResponse>;
    inherited?: Array<PublicFeatureResponse>;
    manual?: Array<PublicFeatureResponse>;
    manual_assignments?: Array<FeatureLinkPayload>;
    disabled_feature_ids?: Array<number>;
};

