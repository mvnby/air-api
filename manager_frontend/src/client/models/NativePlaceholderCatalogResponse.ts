/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { NativePlaceholderConditionItem } from './NativePlaceholderConditionItem';
import type { NativePlaceholderDescriptorItem } from './NativePlaceholderDescriptorItem';
import type { NativePlaceholderTableItem } from './NativePlaceholderTableItem';
export type NativePlaceholderCatalogResponse = {
    document_type: string;
    fields: Array<NativePlaceholderDescriptorItem>;
    conditions: Array<NativePlaceholderConditionItem>;
    tables: Array<NativePlaceholderTableItem>;
};

