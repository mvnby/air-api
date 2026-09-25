/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CartItemPayload } from './CartItemPayload';
import type { CustomerPayload } from './CustomerPayload';
import type { PublicInstallationAcceptance } from './PublicInstallationAcceptance';
export type OrderPayload = {
    customer: CustomerPayload;
    items: Array<CartItemPayload>;
    comment?: (string | null);
    installation_acceptance?: (PublicInstallationAcceptance | null);
};

