/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { TelegramProfile } from './TelegramProfile';
export type TelegramChallengeStartResponse = {
    challenge_id: string;
    expires_at: string;
    status: 'pending' | 'claimed' | 'confirmed' | 'expired' | 'canceled' | 'approval_pending' | 'approved' | 'denied' | 'completed';
    telegram?: (TelegramProfile | null);
    deep_link: string;
    browser_code?: (string | null);
};

