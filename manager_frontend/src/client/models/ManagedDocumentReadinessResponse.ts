/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { DocumentCustomerMissingField } from './DocumentCustomerMissingField';
export type ManagedDocumentReadinessResponse = {
    checked: boolean;
    missing_fields?: Array<DocumentCustomerMissingField>;
    can_issue: boolean;
    template_id: number;
    template_version_id: number;
};

