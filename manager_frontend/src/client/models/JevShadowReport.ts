/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JevShadowItem } from './JevShadowItem';
export type JevShadowReport = {
    queued: number;
    running: number;
    completed: number;
    failed: number;
    comparable: number;
    agreements: number;
    disagreements: number;
    estimated_usd: number;
    input_tokens: number;
    median_duration_ms: (number | null);
    items: Array<JevShadowItem>;
};

