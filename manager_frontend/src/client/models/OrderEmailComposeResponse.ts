/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderEmailMissingRequisiteResponse } from './OrderEmailMissingRequisiteResponse';
import type { OrderEmailTemplateOptionResponse } from './OrderEmailTemplateOptionResponse';
export type OrderEmailComposeResponse = {
    template_key: string;
    template_options?: Array<OrderEmailTemplateOptionResponse>;
    subject: string;
    body_text: string;
    document_ids?: Array<number>;
    document_labels?: Array<string>;
    missing_requisites?: Array<OrderEmailMissingRequisiteResponse>;
};

