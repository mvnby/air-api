/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderServiceLinePayload } from './ManagerOrderServiceLinePayload';
import type { ManagerServiceDescriptionMode } from './ManagerServiceDescriptionMode';
import type { ManagerServiceEstimateOrderLinesMode } from './ManagerServiceEstimateOrderLinesMode';
export type ManagerServiceEstimateOrderLinesResponse = {
    estimate_id: number;
    mode: ManagerServiceEstimateOrderLinesMode;
    description_mode: ManagerServiceDescriptionMode;
    title: string;
    services: Array<ManagerOrderServiceLinePayload>;
};

