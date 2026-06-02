/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EmailLeadImportResponse } from './EmailLeadImportResponse';
export type EmailLeadImportJobResponse = {
    status: string;
    source?: (string | null);
    dry_run?: boolean;
    lookback_days?: (number | null);
    started_at?: (string | null);
    finished_at?: (string | null);
    last_import_at?: (string | null);
    notified_admins?: number;
    already_running?: boolean;
    error?: (string | null);
    message?: (string | null);
    result?: (EmailLeadImportResponse | null);
};

