/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JsonValue } from './JsonValue';
import type { NativeTender } from './NativeTender';
import type { TenderProfile } from './TenderProfile';
export type NativeOpportunity = {
    id: number;
    profile: TenderProfile;
    score?: (number | null);
    relevance_status: string;
    eligible: boolean;
    reason?: (string | null);
    updated_at: string;
    ai_analysis?: (Record<string, JsonValue> | null);
    tender: NativeTender;
};

