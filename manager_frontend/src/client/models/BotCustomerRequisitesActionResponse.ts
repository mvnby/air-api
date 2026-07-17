/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotCustomerBriefResponse } from './BotCustomerBriefResponse';
import type { BotCustomerRequisitesRecognitionResponse } from './BotCustomerRequisitesRecognitionResponse';
export type BotCustomerRequisitesActionResponse = {
    recognition: BotCustomerRequisitesRecognitionResponse;
    customer?: (BotCustomerBriefResponse | null);
    changed: boolean;
};

