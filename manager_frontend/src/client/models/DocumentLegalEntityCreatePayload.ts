/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentLegalEntityRequisites } from './DocumentLegalEntityRequisites';
import type { EnvelopeBranding } from './EnvelopeBranding';
export type DocumentLegalEntityCreatePayload = {
    display_name: string;
    slug?: (string | null);
    legal_name?: (string | null);
    unp?: (string | null);
    entity_type?: string;
    is_vat_payer?: boolean;
    is_default?: boolean;
    requisites?: DocumentLegalEntityRequisites;
    envelope_branding?: EnvelopeBranding;
};

