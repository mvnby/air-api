/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EnvelopeBranding } from './EnvelopeBranding';
import type { EnvelopeParty } from './EnvelopeParty';
export type EnvelopePrintPayload = {
    format?: 'DL' | 'C6' | 'C5' | 'C4';
    sender: EnvelopeParty;
    recipient: EnvelopeParty;
    branding?: (EnvelopeBranding | null);
};

