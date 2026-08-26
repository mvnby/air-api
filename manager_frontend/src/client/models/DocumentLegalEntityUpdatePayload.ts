/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentLegalEntityRequisites } from './DocumentLegalEntityRequisites';
export type DocumentLegalEntityUpdatePayload = {
    display_name?: (string | null);
    slug?: (string | null);
    legal_name?: (string | null);
    unp?: (string | null);
    is_vat_payer?: (boolean | null);
    is_default?: (boolean | null);
    requisites?: (DocumentLegalEntityRequisites | null);
    status?: (string | null);
};

