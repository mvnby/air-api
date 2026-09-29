/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ContractRisk } from './ContractRisk';
export type ContractReviewResponse = {
    attachment_id: number;
    filename: string;
    content_sha256: string;
    model: string;
    pages: (number | null);
    risks: Array<ContractRisk>;
    note: string;
};

