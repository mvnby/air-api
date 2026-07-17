/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotQuickOrderAddressCheck } from './BotQuickOrderAddressCheck';
export type BotQuickOrderDraft = {
    name?: (string | null);
    phone?: (string | null);
    address?: (string | null);
    service_type?: ('turnkey' | 'install_only' | 'pre_install' | 'maintenance' | 'repair' | 'dismantling' | null);
    service_label: string;
    target_date?: (string | null);
    request_text: string;
    parser?: 'fallback' | 'ai';
    address_check?: (BotQuickOrderAddressCheck | null);
};

