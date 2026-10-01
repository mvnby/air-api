/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SourceEquipmentPrefillItem } from './SourceEquipmentPrefillItem';
export type SourceEquipmentPrefillResult = {
    proposal_id?: (number | null);
    added?: Array<SourceEquipmentPrefillItem>;
    skipped?: Array<SourceEquipmentPrefillItem>;
    warnings?: Array<string>;
};

