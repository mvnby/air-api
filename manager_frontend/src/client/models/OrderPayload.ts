/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CartItemPayload } from './CartItemPayload';
import type { CustomerPayload } from './CustomerPayload';
import type { PublicInstallationAcceptance } from './PublicInstallationAcceptance';
import type { WebsiteSubmissionContext } from './WebsiteSubmissionContext';
export type OrderPayload = {
    submission_context?: (WebsiteSubmissionContext | null);
    customer: CustomerPayload;
    items: Array<CartItemPayload>;
    comment?: (string | null);
    installation_acceptance?: (PublicInstallationAcceptance | null);
};

