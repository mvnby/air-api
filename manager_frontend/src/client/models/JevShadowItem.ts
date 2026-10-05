/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type JevShadowItem = {
    id: number;
    source: 'email' | 'belzakupki';
    subject: string;
    state: string;
    created_at: string;
    status: 'queued' | 'running' | 'completed' | 'failed';
    primary_provider: string;
    primary_model_requested: (string | null);
    primary_is_relevant: (boolean | null);
    primary_duration_ms: (number | null);
    model: (string | null);
    kind: (string | null);
    kind_confidence: (number | null);
    hvac_probability: (number | null);
    jev_is_relevant: (boolean | null);
    duration_ms: (number | null);
    input_tokens: (number | null);
    estimated_usd: (number | null);
    error_code: (string | null);
};

