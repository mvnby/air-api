/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CallDriveStatus = {
    connected: boolean;
    pipeline_enabled: boolean;
    transcription_configured: boolean;
    transcription_provider?: 'groq' | 'google_batch' | 'soniox';
    google_batch_configured?: boolean;
    groq_configured?: boolean;
    soniox_configured?: boolean;
    account_label?: (string | null);
    folder_id?: (string | null);
    folder_name?: (string | null);
    folder_url?: (string | null);
    auto_poll_enabled?: boolean;
    last_error_code?: (string | null);
    max_bytes?: number;
    max_duration_seconds?: number;
    max_files_per_poll?: number;
    max_recordings_per_day?: number;
    max_stage_attempts?: number;
    transcription_model: string;
    structure_model: string;
};

