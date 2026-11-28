/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotReserveCandidate } from './BotReserveCandidate';
import type { BotReserveRequest } from './BotReserveRequest';
export type BotReserveLine = {
    id: number;
    title: string;
    quantity: number;
    remaining_quantity: (number | null);
    candidates: Array<BotReserveCandidate>;
    requests: Array<BotReserveRequest>;
};

