/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WebsiteInterestItem } from './WebsiteInterestItem';
/**
 * Optional consented attention, separate from the customer's requested work.
 */
export type WebsiteInterests = {
    version: number;
    consent: boolean;
    items: Array<WebsiteInterestItem>;
};

