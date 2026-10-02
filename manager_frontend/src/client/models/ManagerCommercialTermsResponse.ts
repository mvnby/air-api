/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BusinessDocumentTermsPayload_Output } from './BusinessDocumentTermsPayload_Output';
import type { CommercialSourceTerm } from './CommercialSourceTerm';
export type ManagerCommercialTermsResponse = {
    order_id: number;
    revision?: number;
    customer_requested?: Array<CommercialSourceTerm>;
    proposed?: (BusinessDocumentTermsPayload_Output | null);
    suggested?: (BusinessDocumentTermsPayload_Output | null);
    confirmed?: boolean;
    warnings?: Array<string>;
};

