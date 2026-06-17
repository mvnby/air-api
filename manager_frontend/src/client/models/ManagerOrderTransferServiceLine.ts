/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderTransferServiceRef } from './ManagerOrderTransferServiceRef';
export type ManagerOrderTransferServiceLine = {
    source_id?: (number | null);
    service?: (ManagerOrderTransferServiceRef | null);
    title: string;
    quantity: number;
    price: number;
    cost?: number;
};

