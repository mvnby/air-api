/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerAccessoryItem } from './ManagerAccessoryItem';
export type ManagerAccessoriesWorkspace = {
    target_type: 'series' | 'product';
    target_id: number;
    series_id?: (number | null);
    items?: Array<ManagerAccessoryItem>;
};

