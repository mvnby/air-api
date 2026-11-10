/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * User-maintained facts for document review, not legal certification.
 */
export type IssuerTaxProfile = {
    regime?: (string | null);
    vat_basis?: (string | null);
    /**
     * Date from which this profile is used for documents; not necessarily the regime start date.
     */
    effective_from?: (string | null);
    verified_at?: (string | null);
    official_source?: (string | null);
    confirmation_basis?: (string | null);
};

