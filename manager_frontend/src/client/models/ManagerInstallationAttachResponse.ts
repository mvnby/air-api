/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationAttachedLine } from './ManagerInstallationAttachedLine';
export type ManagerInstallationAttachResponse = {
    estimate_id: number;
    revision: number;
    order_id: number;
    proposal_id: number;
    mode: 'collapsed' | 'detailed';
    total: string;
    lines: Array<ManagerInstallationAttachedLine>;
};

