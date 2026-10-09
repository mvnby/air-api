/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JsonValue } from './JsonValue';
export type NativeTender = {
    id?: (number | null);
    source: string;
    external_id: string;
    title: string;
    customer_name?: (string | null);
    url?: (string | null);
    deadline_at?: (string | null);
    deadline_kind?: string;
    published_at?: (string | null);
    estimated_value?: (number | null);
    currency?: (string | null);
    location?: (string | null);
    quantity?: (number | null);
    summary?: (string | null);
    contacts?: (Array<Record<string, JsonValue>> | null);
    ai_analysis?: (Record<string, JsonValue> | null);
};

