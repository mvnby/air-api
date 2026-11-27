/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotScheduleEvent } from './BotScheduleEvent';
export type BotScheduleResponse = {
    today: string;
    tomorrow: string;
    timezone?: string;
    events: Array<BotScheduleEvent>;
};

