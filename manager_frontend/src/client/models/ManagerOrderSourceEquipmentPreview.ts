/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SourceEquipmentCandidateItem } from './SourceEquipmentCandidateItem';
export type ManagerOrderSourceEquipmentPreview = {
    order_id: number;
    proposal_id?: (number | null);
    proposal_status?: (string | null);
    preview_fingerprint: string;
    items?: Array<SourceEquipmentCandidateItem>;
    warnings?: Array<string>;
};

