/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CallProposalResponse } from './CallProposalResponse';
export type CallRecordingResponse = {
    id: number;
    version: number;
    file_id: string;
    source_version: string;
    source_checksum: string;
    source_size: number;
    source_url: string;
    filename: string;
    mime_type: string;
    origin: string;
    call_occurred_at: (string | null);
    time_source: string;
    phone: (string | null);
    state: string;
    stage: string;
    stage_attempts: Record<string, any>;
    last_error_code: (string | null);
    transcript?: (string | null);
    structure?: (Record<string, any> | null);
    audio_duration_seconds: (number | null);
    proposals?: Array<CallProposalResponse>;
};

